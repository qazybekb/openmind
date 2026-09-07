"""Decide what is due, what it is worth, and when to start it.

All of this is arithmetic, so it happens here rather than in the model: a wrong grade
weight or a deadline shifted by a day is worse than an unhelpful answer. Every function
in this module is pure — feed it Canvas dictionaries and a reference time and it returns
the same answer every time, which is what makes the golden tests in `test_agenda.py`
meaningful.

The rule the student sees, in one sentence: *anything past due and not submitted is
listed first; HIGH means due within 2 days or worth 20% or more of the grade; MED means
due within 5 days; and within a level, items are ordered by when you need to start.*
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Final, Literal

from openmind.timeutil import cal_days, human, human_date, iso, to_local

# -- ranges ------------------------------------------------------------------

Range = Literal["today", "this_week", "next_7_days", "2weeks", "month"]
RANGES: Final[tuple[str, ...]] = ("today", "this_week", "next_7_days", "2weeks", "month")

OVERDUE_LOOKBACK_DAYS: Final[int] = 14

PLANNABLE_TYPES: Final[frozenset[str]] = frozenset(
    {"assignment", "quiz", "discussion_topic", "assessment_request", "sub_assignment"}
)

Status = Literal[
    "excused", "graded", "submitted", "submitted_late", "missing", "missing_locked",
    "past_due_offline", "unsubmitted", "undated",
]
OVERDUE_STATUSES: Final[frozenset[str]] = frozenset({"missing", "missing_locked", "past_due_offline"})
DONE_STATUSES: Final[frozenset[str]] = frozenset({"excused", "graded", "submitted", "submitted_late"})

Priority = Literal["HIGH", "MED", "LOW"]
_LABEL_RANK: Final[dict[str, int]] = {"HIGH": 0, "MED": 1, "LOW": 2}
_LEVELS: Final[tuple[str, ...]] = ("LOW", "MED", "HIGH")

HEAVY_WEIGHT_PCT: Final[float] = 20.0
HIGH_DAYS: Final[int] = 2
MED_DAYS: Final[int] = 5
MIN_HEAVY_POINTS: Final[float] = 50.0
QUICK_TASK_HOURS: Final[float] = 0.5

OFFLINE_SUBMISSION_TYPES: Final[frozenset[str]] = frozenset({"on_paper", "none", "external_tool", "not_graded"})


def resolve_range(name: str, reference: datetime) -> tuple[date, date]:
    """Return the local (start, end) dates a range name covers."""
    today = reference.date()
    if name == "today":
        return today, today
    if name == "this_week":
        return today, today + timedelta(days=6 - today.weekday())
    if name == "2weeks":
        return today, today + timedelta(days=14)
    if name == "month":
        return today, today + timedelta(days=30)
    return today, today + timedelta(days=7)


# -- weights -----------------------------------------------------------------


@dataclass(frozen=True)
class WeightTable:
    """How much each assignment in a course is worth, as a percent of the final grade."""

    by_assignment: dict[str, float] = field(default_factory=dict)
    points_by_assignment: dict[str, float] = field(default_factory=dict)
    quiz_to_assignment: dict[str, str] = field(default_factory=dict)
    basis: Literal["groups", "points", "unknown"] = "unknown"
    note: str | None = None
    median_points: float = 0.0

    def weight_of(self, assignment_id: str | None) -> float | None:
        """Return the percent of the course grade an assignment carries."""
        if assignment_id is None:
            return None
        return self.by_assignment.get(str(assignment_id))

    def points_of(self, assignment_id: str | None) -> float | None:
        """Return an assignment's points possible."""
        if assignment_id is None:
            return None
        return self.points_by_assignment.get(str(assignment_id))


def build_weight_table(groups: list[dict[str, Any]], *, apply_group_weights: bool) -> WeightTable:
    """Turn Canvas assignment groups into a per-assignment weight table.

    Weighted courses divide each group's weight across the group's graded assignments in
    proportion to points. Unweighted courses are points out of the course total. When a
    group has no gradeable points its weight cannot be distributed, so those assignments
    are left unknown rather than guessed at.
    """
    by_assignment: dict[str, float] = {}
    points_by_assignment: dict[str, float] = {}
    quiz_to_assignment: dict[str, str] = {}
    notes: list[str] = []
    all_points: list[float] = []

    per_group: list[tuple[float, list[tuple[str, float]]]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        weight = _as_float(group.get("group_weight")) or 0.0
        rules = group.get("rules")
        if isinstance(rules, dict) and (rules.get("drop_lowest") or rules.get("drop_highest")):
            name = str(group.get("name") or "a group")
            notes.append(f"{name} drops some scores, so the real weight per item may differ")
        entries: list[tuple[str, float]] = []
        for assignment in group.get("assignments") or []:
            if not isinstance(assignment, dict):
                continue
            aid = str(assignment.get("id") or "")
            if not aid:
                continue
            points = _as_float(assignment.get("points_possible"))
            if points is not None:
                points_by_assignment[aid] = points
                all_points.append(points)
            quiz_id = assignment.get("quiz_id")
            if quiz_id:
                quiz_to_assignment[str(quiz_id)] = aid
            omitted = bool(assignment.get("omit_from_final_grade"))
            published = assignment.get("published", True)
            if omitted or not published or not points or points <= 0:
                continue
            entries.append((aid, points))
        per_group.append((weight, entries))

    median_points = _median([p for p in all_points if p > 0])

    if apply_group_weights and any(weight > 0 for weight, _ in per_group):
        for weight, entries in per_group:
            total = sum(points for _, points in entries)
            if weight <= 0 or total <= 0:
                continue
            for aid, points in entries:
                by_assignment[aid] = weight * points / total
        basis: Literal["groups", "points", "unknown"] = "groups"
    else:
        total = sum(points for _, entries in per_group for _, points in entries)
        if total > 0:
            for _, entries in per_group:
                for aid, points in entries:
                    by_assignment[aid] = 100.0 * points / total
            basis = "points"
        else:
            basis = "unknown"

    return WeightTable(
        by_assignment=by_assignment,
        points_by_assignment=points_by_assignment,
        quiz_to_assignment=quiz_to_assignment,
        basis=basis,
        note="; ".join(notes) or None,
        median_points=median_points,
    )


# -- estimates ---------------------------------------------------------------

_KEYWORD_HOURS: Final[tuple[tuple[str, float], ...]] = (
    # Paperwork first: a "Final Project Team Interest Form" is a form, whatever it is
    # a form for. A "Survey of ..." paper is still a paper, so `survey` stays lower down.
    (r"\bforms?\b|questionnaire|\bconsent\b|\brsvp\b|get to know|intake|acknowledg", 0.25),
    (r"final\s*(project|paper)|capstone|thesis|dissertation", 15.0),
    (r"\bfinal\b", 8.0),
    (r"midterm|\bexam\b|\btest\b", 4.0),
    (r"presentation|slide deck|\bslides\b|\bdemo\b", 4.0),
    (r"project|report|essay|case study|\bpaper\b", 6.0),
    (r"\blab\b|\bpset\b|problem set|homework|\bhw\b|exercise|worksheet", 2.5),
    (r"reflection|response|\bmemo\b|journal|short answer|discussion post", 1.5),
    (r"reading|chapter|textbook", 0.75),
    (r"survey|\bpoll\b|attendance|check-?in|sign-?up|syllabus quiz", 0.25),
)

_TYPE_HOURS: Final[dict[str, float]] = {
    "quiz": 0.5,
    "discussion_topic": 0.75,
    "assessment_request": 0.75,
}


@dataclass(frozen=True)
class Estimate:
    """How long something should take, and how much to trust that."""

    hours: float
    confidence: Literal["medium", "low"]


def estimate_hours(title: str, plannable_type: str, points: float | None, weight_pct: float | None) -> Estimate:
    """Estimate the hours an item needs, from its type, then its title, then its points.

    These are rough by design: their job is to order work and set a start-by date, not
    to predict anyone's evening. The weight floors stop a 30%-of-grade "Project 2" from
    looking like a two-hour task just because the title is plain.
    """
    lowered = title.lower()
    hours: float | None = None
    confidence: Literal["medium", "low"] = "low"

    if plannable_type == "quiz":
        if re.search(r"\bfinal\b", lowered):
            hours, confidence = 8.0, "medium"
        elif re.search(r"midterm|\bexam\b", lowered):
            hours, confidence = 4.0, "medium"
        else:
            hours, confidence = _TYPE_HOURS["quiz"], "medium"
    elif plannable_type in _TYPE_HOURS:
        hours, confidence = _TYPE_HOURS[plannable_type], "medium"

    if hours is None or hours <= 1.0:
        for pattern, keyword_hours in _KEYWORD_HOURS:
            if re.search(pattern, lowered):
                if hours is None or keyword_hours > hours:
                    hours, confidence = keyword_hours, "medium"
                break

    if hours is None:
        hours = min(max((points or 0.0) / 10.0, 0.5), 8.0)
        confidence = "low"

    if weight_pct is not None:
        if weight_pct >= 20.0:
            hours = max(hours, 6.0)
        elif weight_pct >= 10.0:
            hours = max(hours, 3.0)

    return Estimate(hours=round(hours, 2), confidence=confidence)


def start_by(due_local: datetime | None, hours: float, reference: datetime, capacity: float) -> tuple[date | None, bool]:
    """Return the day to start, and whether the honest start date has already passed."""
    if due_local is None:
        return None, False
    today = reference.date()
    if hours <= QUICK_TASK_HOURS:
        raw = due_local.date()
    else:
        days_needed = max(1, math.ceil(hours / max(capacity, 0.5)))
        raw = due_local.date() - timedelta(days=days_needed - 1)
    return max(today, raw), raw <= today


# -- status ------------------------------------------------------------------


def classify_status(item: dict[str, Any], due_local: datetime | None, lock_local: datetime | None,
                    submission_types: list[str], reference: datetime) -> Status:
    """Decide where an item stands, checking the strongest signal first."""
    flags = item.get("submissions")
    flags = flags if isinstance(flags, dict) else {}

    if flags.get("excused"):
        return "excused"
    if flags.get("graded"):
        return "graded"
    if flags.get("submitted"):
        return "submitted_late" if flags.get("late") else "submitted"
    if flags.get("missing"):
        return "missing"
    if due_local is None:
        return "undated"
    if due_local < reference:
        if lock_local is not None and lock_local < reference:
            return "missing_locked"
        if submission_types and all(t in OFFLINE_SUBMISSION_TYPES for t in submission_types):
            return "past_due_offline"
        return "missing"
    return "unsubmitted"


# -- items -------------------------------------------------------------------


@dataclass
class AgendaItem:
    """One thing the student has to do, with everything needed to rank it."""

    course_id: str
    course: str
    title: str
    plannable_type: str
    assignment_id: str | None
    html_url: str | None
    due_local: datetime | None
    lock_local: datetime | None
    status: Status
    points: float | None
    weight_pct: float | None
    weight_basis: str
    weight_note: str | None
    est_hours: float
    est_confidence: str
    start_by: date | None
    start_now: bool
    priority: Priority
    reason: str
    days: int | None

    def to_dict(self, reference: datetime) -> dict[str, Any]:
        """Render for a tool payload, with both machine and human forms of each date."""
        payload: dict[str, Any] = {
            "course_id": self.course_id,
            "course": self.course,
            "title": self.title,
            "type": self.plannable_type,
            "status": self.status,
            "due_local": iso(self.due_local),
            "due_human": human(self.due_local, reference=reference),
            "days": self.days,
            "priority": self.priority,
            "reason": self.reason,
            "est_hours": self.est_hours,
        }
        # Every field here costs about 25 bytes per item, and a page is budgeted in bytes:
        # a two-week window on a real account runs to 17 items, so the item stays lean.
        # `est_confidence` is only worth stating when it is not the common "low"; the
        # machine-readable `start_by` date is derivable from `start_by_human`; the URL
        # follows the pattern given in the server instructions from the two ids.
        if self.est_confidence != "low":
            payload["est_confidence"] = self.est_confidence
        if self.assignment_id:
            payload["assignment_id"] = self.assignment_id
        if self.points is not None:
            payload["points"] = self.points
        if self.weight_pct is not None:
            payload["weight_pct"] = round(self.weight_pct, 1)
            payload["weight_basis"] = self.weight_basis
        if self.weight_note:
            payload["weight_note"] = self.weight_note
        if self.start_by is not None:
            payload["start_by"] = human_date(self.start_by)
        if self.start_now:
            payload["start_note"] = "start now"
        if self.lock_local is not None and self.status in ("missing", "unsubmitted"):
            payload["lock_human"] = human(self.lock_local, reference=reference)
        return payload


def build_item(raw: dict[str, Any], *, course_id: str, course_name: str, weights: WeightTable, tz: str,
               reference: datetime, capacity: float) -> AgendaItem | None:
    """Turn one Planner item into a ranked agenda item."""
    plannable_type = str(raw.get("plannable_type") or "")
    if plannable_type not in PLANNABLE_TYPES:
        return None

    plannable = raw.get("plannable")
    plannable = plannable if isinstance(plannable, dict) else {}
    title = str(plannable.get("title") or raw.get("plannable_title") or "Untitled").strip()

    assignment_id = _resolve_assignment_id(raw, plannable, plannable_type, weights)
    due_local = to_local(raw.get("plannable_date") or plannable.get("due_at") or plannable.get("todo_date"), tz)
    lock_local = to_local(plannable.get("lock_at"), tz)

    points = _as_float(plannable.get("points_possible"))
    if points is None:
        points = weights.points_of(assignment_id)

    submission_types = [str(t) for t in (plannable.get("submission_types") or []) if t]
    status = classify_status(raw, due_local, lock_local, submission_types, reference)

    weight_pct = weights.weight_of(assignment_id)
    heavy_note: str | None = None
    if weight_pct is None and points is not None and points > 0:
        threshold = max(MIN_HEAVY_POINTS, 3.0 * weights.median_points) if weights.median_points else MIN_HEAVY_POINTS
        if points >= threshold:
            heavy_note = f"{points:g} pts; weight unknown"

    estimate = estimate_hours(title, plannable_type, points, weight_pct)
    start_day, start_now = start_by(due_local, estimate.hours, reference, capacity)
    days = cal_days(due_local, reference)
    heavy = (weight_pct is not None and weight_pct >= HEAVY_WEIGHT_PCT) or heavy_note is not None
    priority, reason = _prioritise(status, days, heavy, weight_pct, heavy_note, estimate.hours, start_now)

    return AgendaItem(
        course_id=course_id,
        course=course_name,
        title=title,
        plannable_type=plannable_type,
        assignment_id=assignment_id,
        html_url=str(raw.get("html_url") or "") or None,
        due_local=due_local,
        lock_local=lock_local,
        status=status,
        points=points,
        weight_pct=weight_pct,
        weight_basis=weights.basis,
        weight_note=heavy_note or weights.note,
        est_hours=estimate.hours,
        est_confidence=estimate.confidence,
        start_by=start_day,
        start_now=start_now and status not in DONE_STATUSES,
        priority=priority,
        reason=reason,
        days=days,
    )


def build_item_from_assignment(raw: dict[str, Any], *, course_id: str, course_name: str, weights: WeightTable,
                               tz: str, reference: datetime, capacity: float) -> AgendaItem | None:
    """Build an agenda item from the assignments endpoint.

    This is the fallback for Canvas instances that deny Planner access, and the only
    source that can answer ``status="all"`` or ``status="undated"``.
    """
    aid = str(raw.get("id") or "")
    if not aid:
        return None
    title = str(raw.get("name") or "Untitled").strip()
    due_local = to_local(raw.get("due_at"), tz)
    lock_local = to_local(raw.get("lock_at"), tz)
    points = _as_float(raw.get("points_possible"))
    submission_types = [str(t) for t in (raw.get("submission_types") or []) if t]

    submission = raw.get("submission")
    submission = submission if isinstance(submission, dict) else {}
    workflow = str(submission.get("workflow_state") or "")
    shim = {
        "submissions": {
            "excused": bool(submission.get("excused")),
            "graded": workflow == "graded" and submission.get("score") is not None,
            "submitted": bool(submission.get("submitted_at")),
            "late": bool(submission.get("late")),
            "missing": bool(submission.get("missing")),
        }
    }
    status = classify_status(shim, due_local, lock_local, submission_types, reference)

    weight_pct = weights.weight_of(aid)
    heavy_note: str | None = None
    if weight_pct is None and points is not None and points > 0:
        threshold = max(MIN_HEAVY_POINTS, 3.0 * weights.median_points) if weights.median_points else MIN_HEAVY_POINTS
        if points >= threshold:
            heavy_note = f"{points:g} pts; weight unknown"

    plannable_type = "quiz" if raw.get("quiz_id") else "assignment"
    estimate = estimate_hours(title, plannable_type, points, weight_pct)
    start_day, start_now = start_by(due_local, estimate.hours, reference, capacity)
    days = cal_days(due_local, reference)
    heavy = (weight_pct is not None and weight_pct >= HEAVY_WEIGHT_PCT) or heavy_note is not None
    priority, reason = _prioritise(status, days, heavy, weight_pct, heavy_note, estimate.hours, start_now)

    return AgendaItem(
        course_id=course_id,
        course=course_name,
        title=title,
        plannable_type=plannable_type,
        assignment_id=aid,
        html_url=str(raw.get("html_url") or "") or None,
        due_local=due_local,
        lock_local=lock_local,
        status=status,
        points=points,
        weight_pct=weight_pct,
        weight_basis=weights.basis,
        weight_note=heavy_note or weights.note,
        est_hours=estimate.hours,
        est_confidence=estimate.confidence,
        start_by=start_day,
        start_now=start_now and status not in DONE_STATUSES,
        priority=priority,
        reason=reason,
        days=days,
    )


def _prioritise(status: str, days: int | None, heavy: bool, weight_pct: float | None, heavy_note: str | None,
                hours: float, start_now: bool) -> tuple[Priority, str]:
    """Assign a priority label and the one-line reason behind it."""
    if status in OVERDUE_STATUSES:
        return "HIGH", "past due and not submitted"
    if status in DONE_STATUSES:
        return "LOW", f"already {status.replace('_', ' ')}"
    if days is None:
        return "LOW", "no due date"

    when = "due today" if days == 0 else "due tomorrow" if days == 1 else f"due in {days} days"
    heavy_reason = (
        f"worth {weight_pct:.0f}% of grade" if weight_pct is not None and weight_pct >= HEAVY_WEIGHT_PCT
        else heavy_note
    )

    reasons: list[str] = []
    if days <= HIGH_DAYS:
        label: Priority = "HIGH"
        reasons.append(when)
        if heavy_reason:
            reasons.append(heavy_reason)
    elif heavy:
        label = "HIGH"
        reasons.append(heavy_reason or "high point value")
        reasons.append(when)
    elif days <= MED_DAYS:
        label = "MED"
        reasons.append(when)
    else:
        label = "LOW"
        reasons.append(when)

    if label != "HIGH" and start_now:
        label = _LEVELS[min(_LEVELS.index(label) + 1, len(_LEVELS) - 1)]
        reasons.append(f"~{hours:g}h, start now")

    return label, "; ".join(reasons)


def sort_items(items: list[AgendaItem]) -> list[AgendaItem]:
    """Order upcoming work by urgency, then by when it has to be started."""
    far_future = date.max

    def key(item: AgendaItem) -> tuple[Any, ...]:
        return (
            _LABEL_RANK.get(item.priority, 3),
            item.start_by or far_future,
            item.due_local.timestamp() if item.due_local else float("inf"),
            -(item.weight_pct or 0.0),
            item.course.lower(),
            item.title.lower(),
        )

    return sorted(items, key=key)


def sort_overdue(items: list[AgendaItem]) -> list[AgendaItem]:
    """Order overdue work: still-submittable first, most recently due first."""

    def key(item: AgendaItem) -> tuple[Any, ...]:
        locked = item.status == "missing_locked"
        return (locked, -(item.due_local.timestamp() if item.due_local else 0.0), item.course.lower())

    return sorted(items, key=key)


def counts(items: list[AgendaItem], overdue: list[AgendaItem]) -> dict[str, int]:
    """Summarise an agenda so the host can say "3 things, 1 urgent" without counting."""
    return {
        "total": len(items) + len(overdue),
        "overdue": len(overdue),
        "high": sum(1 for item in items if item.priority == "HIGH"),
        "med": sum(1 for item in items if item.priority == "MED"),
        "low": sum(1 for item in items if item.priority == "LOW"),
        "est_hours": round(sum(item.est_hours for item in items if item.status not in DONE_STATUSES), 1),
    }


# -- helpers -----------------------------------------------------------------


def _resolve_assignment_id(raw: dict[str, Any], plannable: dict[str, Any], plannable_type: str,
                           weights: WeightTable) -> str | None:
    """Find the assignment id behind a planner item.

    Quizzes carry the quiz id in ``plannable_id``, and graded discussions carry the
    assignment id inside ``plannable``. Both have to map back to an assignment for the
    weight table to apply.
    """
    if plannable_type == "quiz":
        quiz_id = str(raw.get("plannable_id") or "")
        mapped = weights.quiz_to_assignment.get(quiz_id)
        if mapped:
            return mapped
        inner = plannable.get("assignment_id")
        return str(inner) if inner else None
    if plannable_type in {"discussion_topic", "sub_assignment"}:
        inner = plannable.get("assignment_id")
        if inner:
            return str(inner)
    if plannable_type == "assessment_request":
        inner = plannable.get("assignment_id")
        return str(inner) if inner else None
    plannable_id = raw.get("plannable_id")
    return str(plannable_id) if plannable_id else None


def _as_float(value: object) -> float | None:
    """Coerce a Canvas numeric field to ``float``."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _median(values: list[float]) -> float:
    """Return the median of a list, or 0.0 when empty."""
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0
