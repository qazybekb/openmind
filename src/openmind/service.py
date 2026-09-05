"""Answer academic questions about one student's courses.

This is where the tools' actual work happens. Keeping it out of `server.py` means the
CLI can run the same operations without MCP, the tests can exercise them without a
protocol, and a future transport only has to change how a `Session` is constructed.

Three habits run through every method here:

* **Never present a failure as "nothing due."** A course that fails to load produces
  ``partial: true`` and a warning naming the course, not a shorter list.
* **Every payload is stamped.** ``as_of``, ``tz``, ``partial``, and ``warnings`` are on
  everything, so a host can tell a student when the answer is from and what is missing.
* **Budgets are enforced, not hoped for.** `shrink` trims oversized payloads by dropping
  whole items from the end and saying it did, rather than truncating into invalid JSON.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from openmind import agenda, catalog, index, materials, pedagogy, schedule
from openmind.cache import TTLCache
from openmind.canvas import CanvasClient, CanvasError
from openmind.config import Config
from openmind.timeutil import UTC, human, iso, now, to_local, zone

logger = logging.getLogger(__name__)

INDEX_BUDGET_S: Final[float] = 20.0
OFFERING_CACHE_S: Final[float] = 24 * 3600
MAX_ANNOUNCEMENTS: Final[int] = 10
MAX_RUBRIC_ROWS: Final[int] = 12
MAX_GRADED: Final[int] = 20
# Room kept back for the "continues, call again with cursor=N" line.
_CONTINUATION_ALLOWANCE: Final[int] = 160
# Slack for JSON escaping of the prose plus the cursor field it may add.
_JSON_STRING_OVERHEAD: Final[int] = 220

BUDGETS: Final[dict[str, int]] = {
    "list_courses": 1_500,
    "get_deadlines": 4_000,
    "get_assignment": 5_000,
    "get_course_overview": 6_000,
    "get_grades": 2_000,
    "find_materials": 4_000,
    "read_material": 6_000,
    "prepare_study_session": 6_000,
    "search_catalog": 4_000,
    "get_catalog_course": 3_000,
    "check_offering": 2_000,
    "index_course": 1_000,
}

_LIST_KEYS: Final[tuple[str, ...]] = (
    "items", "courses", "hits", "materials", "sections", "announcements", "modules",
    "evidence", "graded", "overdue", "rubric",
)


class ServiceError(Exception):
    """An operation could not be completed and the student should be told why."""


def encoded_size(payload: Any) -> int:
    """Measure a payload the way the tools serialise it.

    `server._json` emits compact separators, so measuring with Python's spacier default
    made every budget stop several hundred bytes early — a page short of results for no
    reason a student could see.
    """
    return len(json.dumps(payload, default=str, separators=(",", ":")))


def shrink(payload: dict[str, Any], budget: int) -> dict[str, Any]:
    """Trim a payload to a byte budget by dropping list items from the end.

    Silent truncation is the failure mode worth avoiding: a host that receives half a
    list has no way to know it. Dropping whole entries and adding a ``truncated`` note
    keeps the JSON valid and the omission visible.
    """
    if encoded_size(payload) <= budget:
        return payload

    trimmed = dict(payload)
    dropped = 0

    def size_with_note() -> int:
        """Measure the payload as it will actually be returned, note included."""
        preview = dict(trimmed)
        preview["truncated"] = True
        preview["warnings"] = [*(trimmed.get("warnings") or []), _omission_note(dropped or 1)]
        return encoded_size(preview)

    for key in _LIST_KEYS:
        values = trimmed.get(key)
        while isinstance(values, list) and values and size_with_note() > budget:
            values.pop()
            dropped += 1
        if size_with_note() <= budget:
            break

    if dropped:
        trimmed["warnings"] = [*(trimmed.get("warnings") or []), _omission_note(dropped)]
        trimmed["truncated"] = True
    return trimmed


def _omission_note(dropped: int) -> str:
    """Say plainly that results were left out, and what to do about it."""
    return f"{dropped} more result(s) omitted to stay within the response size limit; narrow the query."


def fit_prose(payload: dict[str, Any], field: str, text: str, offset: int, requested: int,
              budget: int, *, cursor_field: str) -> None:
    """Put as much of *text* into the payload as the budget allows, and page the rest.

    `shrink` only drops whole list items, so a single long string sails past the budget
    once every list is empty. A caller asking for 8,000 characters against a 5,000-byte
    tool gets what actually fits and a cursor for the remainder, rather than an
    oversized payload or a silent truncation.
    """
    payload[field] = ""
    payload.pop(cursor_field, None)
    fixed = encoded_size(payload)
    room = max(0, budget - fixed - _JSON_STRING_OVERHEAD)
    take = min(requested, room)

    window, _ = materials.truncate(text, take, offset=offset)
    payload[field] = window
    consumed = offset + len(window)
    if consumed < len(text):
        payload[cursor_field] = consumed


def fit_page(payload: dict[str, Any], records: Sequence[tuple[str, Any]], budget: int) -> int:
    """Fill a payload's list fields with as many records as the budget allows.

    Returns how many records were emitted, which is what a cursor must advance by.
    Deciding the page size *before* handing out a continuation is the whole point: a
    cursor computed from the requested limit and then trimmed by `shrink` skips
    everything in between, and the student never learns those items exist.

    At least one record is always emitted, even if it alone exceeds the budget, because
    a page of zero with a cursor pointing at itself is an infinite loop.
    """
    for key, _ in records:
        payload.setdefault(key, [])

    emitted = 0
    for key, record in records:
        payload[key].append(record)
        if encoded_size(payload) > budget and emitted:
            payload[key].pop()
            break
        emitted += 1
    return emitted


@dataclass
class CourseFacts:
    """The static facts about one enabled course."""

    id: str
    name: str
    nickname: str
    code: str
    term: str
    ends_at: str
    weighted: bool
    current_score: float | None
    current_grade: str | None
    final_score: float | None
    hide_final_grades: bool


class Session:
    """One student's read-only view of bCourses, the catalog, and their own index."""

    def __init__(self, cfg: Config, client: CanvasClient | None = None, *, cache: TTLCache | None = None,
                 clock: datetime | None = None) -> None:
        self.cfg = cfg
        self._client = client
        self.cache = cache if cache is not None else (client.cache if client else TTLCache())
        self.tz = cfg.time_zone
        self._clock = clock

    @property
    def canvas(self) -> CanvasClient:
        """Return the bCourses client, or explain what is missing.

        The catalog and class-schedule tools are public data and work without one, so a
        student can ask "what should I take next semester" before they have decided to
        hand over a Canvas token at all.
        """
        if self._client is None:
            raise ServiceError(
                "That needs your bCourses account. Run `openmind setup` in a terminal, then restart your AI app."
            )
        return self._client

    # -- basics ------------------------------------------------------------

    def now(self) -> datetime:
        """Return the current local time, or the frozen clock in tests."""
        if self._clock is not None:
            return self._clock.astimezone(zone(self.tz))
        return now(self.tz)

    def stamp(self, warnings: list[str] | None = None, *, partial: bool = False) -> dict[str, Any]:
        """Return the provenance fields every payload carries.

        A list that stopped at the client's page limit is folded in here rather than at
        each call site, because the failure it guards against — a short list read as the
        whole set — applies to every payload built from one.
        """
        notes = list(warnings or [])
        if self._client is not None and self._client.incomplete:
            notes.append(
                f"bCourses returned more pages than OpenMind reads in one go for "
                f"{len(self._client.incomplete)} request(s); some records are missing from this answer."
            )
        return {
            "as_of": iso(self.now()),
            "tz": self.tz,
            "partial": partial or bool(notes),
            "warnings": notes,
        }

    # -- courses -----------------------------------------------------------

    def course_facts(self, *, refresh: bool = False) -> tuple[dict[str, CourseFacts], list[str]]:
        """Return the enabled courses, plus warnings for any that could not be read."""
        warnings: list[str] = []
        try:
            raw = self.canvas.courses(refresh=refresh)
        except CanvasError as exc:
            raise ServiceError(str(exc)) from exc

        found: dict[str, CourseFacts] = {}
        for entry in raw:
            course_id = str(entry.get("id") or "")
            if not self.cfg.is_enabled(course_id):
                continue
            term = entry.get("term") if isinstance(entry.get("term"), dict) else {}
            enrollments = [e for e in (entry.get("enrollments") or []) if isinstance(e, dict)]
            student = next((e for e in enrollments if e.get("type") in {"student", "StudentEnrollment"}), None)
            student = student or (enrollments[0] if enrollments else {})
            found[course_id] = CourseFacts(
                id=course_id,
                name=str(entry.get("name") or ""),
                nickname=self.cfg.nickname(course_id),
                code=str(entry.get("course_code") or ""),
                term=str(term.get("name") or ""),
                ends_at=str(term.get("end_at") or entry.get("end_at") or ""),
                weighted=bool(entry.get("apply_assignment_group_weights")),
                current_score=_as_float(student.get("computed_current_score")),
                current_grade=_as_str(student.get("computed_current_grade")),
                final_score=_as_float(student.get("computed_final_score")),
                hide_final_grades=bool(entry.get("hide_final_grades")),
            )

        for course_id, nickname in self.cfg.courses.items():
            if course_id not in found:
                warnings.append(f"{nickname} (course {course_id}) is not in your active bCourses enrolments right now.")
        return found, warnings

    def list_courses(self, *, refresh: bool = False) -> dict[str, Any]:
        """List enabled courses with the student's own score in each."""
        facts, warnings = self.course_facts(refresh=refresh)
        indexed = set(self._indexed_course_ids())
        reference = self.now()

        courses = []
        for course_id, course in facts.items():
            ends = to_local(course.ends_at, self.tz)
            entry: dict[str, Any] = {
                "id": course_id,
                "name": course.name,
                "nickname": course.nickname,
                "indexed": course_id in indexed,
            }
            if course.code:
                entry["code"] = course.code
            if course.term:
                entry["term"] = course.term
            if ends:
                entry["ends_human"] = human(ends, reference=reference)
            if course.current_score is not None:
                entry["current_score"] = course.current_score
            if course.current_grade:
                entry["current_grade"] = course.current_grade
            courses.append(entry)

        payload = {
            "courses": courses,
            "user": {"name": self.cfg.user_name, "tz": self.tz},
            **self.stamp(warnings),
        }
        return shrink(payload, BUDGETS["list_courses"])

    # -- deadlines ---------------------------------------------------------

    def weight_table(self, course_id: str, *, weighted: bool, refresh: bool = False) -> agenda.WeightTable | None:
        """Return a course's weight table, or ``None`` when Canvas would not say."""
        try:
            groups = self.canvas.assignment_groups(course_id, refresh=refresh)
        except CanvasError:
            logger.info("Could not read assignment groups for course %s", course_id)
            return None
        return agenda.build_weight_table(groups, apply_group_weights=weighted)

    def deadlines(self, *, window: str = "next_7_days", course_id: str | None = None, status: str = "open",
                  limit: int = 25, offset: int = 0, refresh: bool = False) -> dict[str, Any]:
        """Return what is due, ranked, with everything needed to act on it."""
        facts, warnings = self.course_facts(refresh=refresh)
        if course_id:
            course_id = self.cfg.require_enabled(course_id)
            facts = {cid: course for cid, course in facts.items() if cid == course_id}
        if not facts:
            raise ServiceError(
                "None of your enabled courses could be read from bCourses. Run `openmind doctor` to check your setup."
            )

        reference = self.now()
        start, end = agenda.resolve_range(window, reference)
        capacity = self.cfg.capacity_hours_per_day

        weights: dict[str, agenda.WeightTable] = {}
        for cid, course in facts.items():
            table = self.weight_table(cid, weighted=course.weighted, refresh=refresh)
            if table is None:
                warnings.append(f"Grade weights for {course.nickname} could not be read; weights are shown as unknown.")
                table = agenda.WeightTable()
            weights[cid] = table

        use_assignments = status in {"all", "undated"}
        items: list[agenda.AgendaItem] = []
        skipped = 0
        source = "planner"

        if not use_assignments:
            try:
                items, skipped = self._planner_items(facts, weights, start, end, reference, capacity, refresh=refresh)
            except CanvasError as exc:
                logger.info("Planner unavailable, falling back to per-course assignments: %s", exc)
                use_assignments = True
                warnings.append("bCourses Planner was unavailable; deadlines came from each course's assignment list.")

        if use_assignments:
            source = "assignments"
            items, failures = self._assignment_items(facts, weights, reference, capacity, refresh=refresh)
            warnings.extend(failures)

        overdue_cutoff = reference - timedelta(days=agenda.OVERDUE_LOOKBACK_DAYS)
        overdue: list[agenda.AgendaItem] = []
        upcoming: list[agenda.AgendaItem] = []
        for item in items:
            if item.status in agenda.OVERDUE_STATUSES:
                if item.due_local is not None and item.due_local >= overdue_cutoff:
                    overdue.append(item)
                continue
            if item.due_local is None:
                if status in {"all", "undated"}:
                    upcoming.append(item)
                continue
            if status == "undated":
                continue
            if not (start <= item.due_local.date() <= end):
                continue
            if status == "open" and item.status in agenda.DONE_STATUSES:
                continue
            if status in {"submitted", "graded", "missing"} and item.status != status and not (
                status == "submitted" and item.status == "submitted_late"
            ):
                continue
            upcoming.append(item)

        overdue = agenda.sort_overdue(overdue)
        upcoming = agenda.sort_items(upcoming)
        totals = agenda.counts(upcoming, overdue)

        # One cursor over both lists, overdue first. Two independent offsets would make
        # "have I seen everything?" unanswerable, and overdue work is what a student most
        # needs to reach.
        records: list[tuple[str, dict[str, Any]]] = [
            *(("overdue", item.to_dict(reference)) for item in overdue),
            *(("items", item.to_dict(reference)) for item in upcoming),
        ]
        offset = max(0, min(offset, len(records)))

        notes: list[str] = []
        if overdue:
            notes.append(
                f"overdue[] covers the last {agenda.OVERDUE_LOOKBACK_DAYS} days regardless of the range asked for, "
                "because work that was never submitted does not stop mattering when the window moves."
            )
        if status == "missing":
            notes.append("Missing work is in overdue[], not items[].")
        if skipped:
            notes.append(f"{skipped} calendar events, pages, or notes were skipped; they are not graded work.")
        if any(w.basis == "unknown" for w in weights.values()):
            notes.append("Some grade weights could not be resolved and are reported as unknown rather than guessed.")
        notes.append(
            "Priority: HIGH = due within 2 days or worth 20%+ of the grade; MED = due within 5 days. "
            f"start_by assumes about {capacity:g} hours of work a day."
        )

        payload: dict[str, Any] = {
            "range": window,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "source": source,
            "overdue": [],
            "items": [],
            "counts": totals,
            "notes": notes,
            **self.stamp(warnings),
        }
        emitted = fit_page(payload, records[offset : offset + limit], BUDGETS["get_deadlines"])
        if offset + emitted < len(records):
            payload["next_offset"] = offset + emitted
            payload["remaining"] = len(records) - (offset + emitted)
        return payload

    def _planner_items(self, facts: dict[str, CourseFacts], weights: dict[str, agenda.WeightTable],
                       start: Any, end: Any, reference: datetime, capacity: float, *,
                       refresh: bool) -> tuple[list[agenda.AgendaItem], int]:
        """Read the Planner, which is the only source with per-student due dates."""
        lookback = reference - timedelta(days=agenda.OVERDUE_LOOKBACK_DAYS)
        finish = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=zone(self.tz))
        raw = self.canvas.planner_items(
            lookback.astimezone(UTC).isoformat(),
            finish.astimezone(UTC).isoformat(),
            list(facts),
            refresh=refresh,
        )

        items: list[agenda.AgendaItem] = []
        skipped = 0
        for entry in raw:
            course_id = str(entry.get("course_id") or "")
            if course_id not in facts:
                skipped += 1
                continue
            if str(entry.get("plannable_type") or "") not in agenda.PLANNABLE_TYPES:
                skipped += 1
                continue
            item = agenda.build_item(
                entry,
                course_id=course_id,
                course_name=facts[course_id].nickname,
                weights=weights[course_id],
                tz=self.tz,
                reference=reference,
                capacity=capacity,
            )
            if item is not None:
                items.append(item)
        return items, skipped

    def _assignment_items(self, facts: dict[str, CourseFacts], weights: dict[str, agenda.WeightTable],
                          reference: datetime, capacity: float, *,
                          refresh: bool) -> tuple[list[agenda.AgendaItem], list[str]]:
        """Read every course's assignment list — the fallback, and the only undated source."""
        items: list[agenda.AgendaItem] = []
        failures: list[str] = []
        for course_id, course in facts.items():
            try:
                raw = self.canvas.assignments(course_id, refresh=refresh)
            except CanvasError as exc:
                failures.append(f"{course.nickname}: {exc}")
                continue
            for entry in raw:
                item = agenda.build_item_from_assignment(
                    entry,
                    course_id=course_id,
                    course_name=course.nickname,
                    weights=weights[course_id],
                    tz=self.tz,
                    reference=reference,
                    capacity=capacity,
                )
                if item is not None:
                    items.append(item)
        return items, failures

    # -- assignment detail -------------------------------------------------

    def assignment(self, course_id: str, assignment_id: str, *, max_chars: int = 3000, cursor: int = 0,
                   refresh: bool = False) -> dict[str, Any]:
        """Return one assignment's facts, description, and rubric."""
        course_id = self.cfg.require_enabled(course_id)
        facts, warnings = self.course_facts(refresh=refresh)
        course = facts.get(course_id)
        try:
            raw = self.canvas.assignment(course_id, assignment_id, refresh=refresh)
        except CanvasError as exc:
            raise ServiceError(str(exc)) from exc
        if not raw:
            raise ServiceError(f"bCourses returned nothing for assignment {assignment_id}.")

        reference = self.now()
        table = self.weight_table(course_id, weighted=bool(course and course.weighted), refresh=refresh)
        weight = table.weight_of(str(assignment_id)) if table else None
        due_local = to_local(raw.get("due_at"), self.tz)
        lock_local = to_local(raw.get("lock_at"), self.tz)
        points = _as_float(raw.get("points_possible"))
        estimate = agenda.estimate_hours(
            str(raw.get("name") or ""), "quiz" if raw.get("quiz_id") else "assignment", points, weight
        )
        start_day, start_now = agenda.start_by(due_local, estimate.hours, reference, self.cfg.capacity_hours_per_day)

        submission = raw.get("submission") if isinstance(raw.get("submission"), dict) else {}
        description_text = materials.html_to_text(str(raw.get("description") or ""))

        payload: dict[str, Any] = {
            "course_id": course_id,
            "course": course.nickname if course else course_id,
            "assignment_id": str(raw.get("id") or assignment_id),
            "title": str(raw.get("name") or "Untitled"),
            "due_local": iso(due_local),
            "due_human": human(due_local, reference=reference),
            "points": points,
            "submission_types": [str(t) for t in (raw.get("submission_types") or [])],
            "est_hours": estimate.hours,
            "est_confidence": estimate.confidence,
            "url": str(raw.get("html_url") or ""),
            "description": "",
            "description_chars": len(description_text),
            "submission": {
                "state": str(submission.get("workflow_state") or "unsubmitted"),
                "submitted_at": str(submission.get("submitted_at") or "") or None,
                "score": _as_float(submission.get("score")),
                "late": bool(submission.get("late")),
                "missing": bool(submission.get("missing")),
                "excused": bool(submission.get("excused")),
                "attempts": submission.get("attempt"),
            },
            **self.stamp(warnings),
        }
        if lock_local is not None:
            payload["lock_human"] = human(lock_local, reference=reference)
        if weight is not None:
            payload["weight_pct"] = round(weight, 1)
            payload["weight_basis"] = table.basis if table else "unknown"
        elif table and table.note:
            payload["weight_note"] = table.note
        if start_day is not None:
            payload["start_by"] = start_day.isoformat()
            if start_now:
                payload["start_note"] = "start now"
        rubric = _rubric(raw)
        if rubric:
            payload["rubric"] = rubric[:MAX_RUBRIC_ROWS]
        if raw.get("allowed_attempts") not in (None, -1):
            payload["allowed_attempts"] = raw.get("allowed_attempts")

        payload = shrink(payload, BUDGETS["get_assignment"])
        fit_prose(payload, "description", description_text, cursor, max_chars,
                  BUDGETS["get_assignment"], cursor_field="description_cursor")
        return payload

    # -- course overview ---------------------------------------------------

    def course_overview(self, course_id: str, *, announcements_days: int = 30, max_chars: int = 4000,
                        cursor: int = 0, refresh: bool = False) -> dict[str, Any]:
        """Return the syllabus, module structure, and recent announcements."""
        course_id = self.cfg.require_enabled(course_id)
        warnings: list[str] = []
        reference = self.now()

        try:
            raw = self.canvas.course(course_id, refresh=refresh)
        except CanvasError as exc:
            raise ServiceError(str(exc)) from exc

        syllabus_text = materials.html_to_text(str(raw.get("syllabus_body") or ""))

        modules: list[dict[str, Any]] = []
        try:
            for module in self.canvas.modules(course_id, refresh=refresh):
                entry: dict[str, Any] = {"name": str(module.get("name") or "Untitled")}
                titles = [
                    str(item.get("title") or "")
                    for item in (module.get("items") or [])
                    if isinstance(item, dict) and item.get("title")
                ]
                if titles:
                    entry["items"] = titles[:12]
                    if len(titles) > 12:
                        entry["more_items"] = len(titles) - 12
                modules.append(entry)
        except CanvasError:
            warnings.append("Module list could not be read for this course.")

        announcements: list[dict[str, Any]] = []
        try:
            days = max(1, min(int(announcements_days), 90))
            window_start = (reference - timedelta(days=days)).astimezone(UTC).isoformat()
            window_end = (reference + timedelta(days=1)).astimezone(UTC).isoformat()
            for post in self.canvas.announcements([course_id], window_start, window_end, refresh=refresh):
                posted = to_local(post.get("posted_at") or post.get("created_at"), self.tz)
                body, _, _ = materials.summarise_html(str(post.get("message") or ""), 400)
                announcements.append({
                    "title": str(post.get("title") or "Untitled"),
                    "posted_human": human(posted, reference=reference),
                    "excerpt": body,
                    "url": str(post.get("html_url") or ""),
                })
        except CanvasError:
            warnings.append("Announcements could not be read for this course.")

        payload: dict[str, Any] = {
            "course_id": course_id,
            "name": str(raw.get("name") or self.cfg.nickname(course_id)),
            "code": str(raw.get("course_code") or ""),
            "syllabus": "",
            "syllabus_chars": len(syllabus_text),
            "modules": modules,
            "announcements": announcements[:MAX_ANNOUNCEMENTS],
            **self.stamp(warnings),
        }
        if not syllabus_text:
            payload["syllabus_note"] = "This course has no syllabus page in bCourses."
        payload = shrink(payload, BUDGETS["get_course_overview"])
        fit_prose(payload, "syllabus", syllabus_text, cursor, max_chars,
                  BUDGETS["get_course_overview"], cursor_field="syllabus_cursor")
        return payload

    # -- grades ------------------------------------------------------------

    def grades(self, course_id: str | None = None, *, refresh: bool = False) -> dict[str, Any]:
        """Return the student's own grades. Never anyone else's."""
        facts, warnings = self.course_facts(refresh=refresh)
        if course_id:
            course_id = self.cfg.require_enabled(course_id)
            facts = {cid: course for cid, course in facts.items() if cid == course_id}

        courses = []
        for cid, course in facts.items():
            entry: dict[str, Any] = {
                "course_id": cid,
                "course": course.nickname,
                "current_score": course.current_score,
                "current_grade": course.current_grade,
            }
            if course.final_score is not None and not course.hide_final_grades:
                entry["final_score"] = course.final_score
            if course.hide_final_grades:
                entry["hide_final_grades"] = True
            if course.current_score is None:
                entry["note"] = "bCourses has no current score for this course yet."
            courses.append(entry)

        payload: dict[str, Any] = {"courses": courses, **self.stamp(warnings)}
        payload["note"] = (
            "Scores come straight from bCourses and cover graded work only. "
            "Ungraded assignments are not counted as zeros."
        )

        if course_id:
            payload.update(self._grade_detail(course_id, facts.get(course_id), refresh=refresh))
        return shrink(payload, BUDGETS["get_grades"])

    def _grade_detail(self, course_id: str, course: CourseFacts | None, *, refresh: bool) -> dict[str, Any]:
        """Break one course down by assignment group and recent graded work."""
        detail: dict[str, Any] = {}
        table = self.weight_table(course_id, weighted=bool(course and course.weighted), refresh=refresh)
        try:
            groups = self.canvas.assignment_groups(course_id, refresh=refresh)
        except CanvasError:
            return {"detail_note": "The grade breakdown for this course could not be read."}

        detail["weighted"] = bool(course and course.weighted)
        detail["groups"] = [
            {
                "name": str(group.get("name") or "Untitled"),
                "weight_pct": _as_float(group.get("group_weight")),
                "assignments": len([a for a in (group.get("assignments") or []) if isinstance(a, dict)]),
            }
            for group in groups
        ]
        if table and table.note:
            detail["weight_note"] = table.note

        try:
            submissions = self.canvas.submissions(course_id, refresh=refresh)
        except CanvasError:
            return detail

        reference = self.now()
        graded: list[dict[str, Any]] = []
        ungraded = 0
        for submission in submissions:
            if submission.get("score") is None or submission.get("workflow_state") != "graded":
                if submission.get("submitted_at"):
                    ungraded += 1
                continue
            assignment = submission.get("assignment") if isinstance(submission.get("assignment"), dict) else {}
            aid = str(submission.get("assignment_id") or "")
            graded.append({
                "title": str(assignment.get("name") or f"Assignment {aid}"),
                "score": _as_float(submission.get("score")),
                "points": _as_float(assignment.get("points_possible")) or (table.points_of(aid) if table else None),
                "graded_human": human(to_local(submission.get("graded_at"), self.tz), reference=reference),
            })
        detail["graded"] = graded[:MAX_GRADED]
        detail["ungraded_count"] = ungraded
        return detail

    # -- materials ---------------------------------------------------------

    def _indexed_course_ids(self) -> list[str]:
        """Return course ids with an index, tolerating a missing database."""
        try:
            with index.connect(create=False) as conn:
                return index.indexed_courses(conn)
        except (index.IndexError_, sqlite3.Error):
            return []

    def find_materials(self, course_id: str, *, query: str = "", kind: str | None = None, limit: int = 10,
                       cursor: int = 0, refresh: bool = False) -> dict[str, Any]:
        """Search or list a course's materials, citing pages when the course is indexed."""
        course_id = self.cfg.require_enabled(course_id)
        warnings: list[str] = []
        limit = max(1, min(int(limit), 25))
        indexed = course_id in self._indexed_course_ids()

        cursor = max(0, int(cursor))
        hits: list[dict[str, Any]] = []
        listing: list[dict[str, Any]] = []
        pending_files = 0
        indexed_at: str | None = None
        # One more than asked for, so "is there another page?" is answered by looking
        # rather than by assuming a full page means more exist.
        window = limit + 1

        if indexed:
            with index.connect() as conn:
                stats = index.course_stats(conn, course_id)
                pending_files = stats.get("pending", 0)
                indexed_at = index.last_indexed_at(conn, course_id)
                if query.strip():
                    hits = [hit.to_dict() for hit in index.search(conn, course_id, query, limit=window, kind=kind,
                                                                  offset=cursor)]
                else:
                    listing = index.list_materials(conn, course_id, kind=kind, limit=window, offset=cursor)
        else:
            listing, hits, warn = self._live_materials(
                course_id, query=query, kind=kind, limit=window, cursor=cursor, refresh=refresh
            )
            warnings.extend(warn)

        payload: dict[str, Any] = {
            "course_id": course_id,
            "course": self.cfg.nickname(course_id),
            "query": query or None,
            "indexed": indexed,
            "hits": [],
            "materials": [],
            **self.stamp(warnings),
        }
        if indexed_at:
            payload["indexed_at"] = indexed_at
        if pending_files:
            payload["pending_files"] = pending_files
            payload["pending_note"] = (
                f"{pending_files} file(s) in this course are not extracted yet. Call index_course to continue."
            )
        if not indexed:
            payload["index_note"] = (
                "This course is not indexed, so search covers titles, module names, the syllabus, and pages — "
                "not the inside of slides or readings. Call index_course to change that."
            )

        candidates = [*(("hits", hit) for hit in hits[:limit]), *(("materials", row) for row in listing[:limit])]
        emitted = fit_page(payload, candidates, BUDGETS["find_materials"])
        if emitted < len(candidates) or len(hits) > limit or len(listing) > limit:
            payload["next_cursor"] = cursor + emitted
        return payload

    def _live_materials(self, course_id: str, *, query: str, kind: str | None, limit: int, cursor: int,
                        refresh: bool) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        """List and search a course's materials without an index.

        Titles, module names, and the small text-native sources are enough to answer
        "where are the week 3 slides"; anything more needs the opt-in index, and the
        payload says so.
        """
        warnings: list[str] = []
        needle = query.strip().lower()
        listing: list[dict[str, Any]] = []
        hits: list[dict[str, Any]] = []

        def matches(*fields: str) -> bool:
            if not needle:
                return True
            haystack = " ".join(fields).lower()
            return all(word in haystack for word in needle.split())

        if kind in (None, "file", "page"):
            try:
                for position, module in enumerate(self.canvas.modules(course_id, refresh=refresh)):
                    module_name = str(module.get("name") or "")
                    for item_position, item in enumerate(module.get("items") or []):
                        if not isinstance(item, dict):
                            continue
                        title = str(item.get("title") or "")
                        item_kind = str(item.get("type") or "").lower()
                        if kind == "file" and item_kind != "file":
                            continue
                        if kind == "page" and item_kind != "page":
                            continue
                        if not matches(title, module_name):
                            continue
                        listing.append({
                            "title": title,
                            "kind": item_kind or "item",
                            "module": module_name,
                            "canvas_id": str(item.get("content_id") or item.get("id") or ""),
                            "url": str(item.get("html_url") or ""),
                            "position": (position, item_position),
                        })
            except CanvasError:
                warnings.append("Module contents could not be read for this course.")

        if needle and kind in (None, "syllabus"):
            try:
                course = self.canvas.course(course_id, refresh=refresh)
                text = materials.html_to_text(str(course.get("syllabus_body") or ""))
                excerpt = _excerpt_around(text, needle)
                if excerpt:
                    hits.append({
                        "kind": "syllabus",
                        "title": "Syllabus",
                        "excerpt": excerpt,
                        "cite": "(Syllabus)",
                    })
            except CanvasError:
                warnings.append("The syllabus could not be read for this course.")

        for entry in listing:
            entry.pop("position", None)
        # Skip before slicing: applying the limit first made every cursor return page one.
        return listing[cursor : cursor + limit], hits[:limit], warnings

    def index_course(self, course_id: str, *, enable: bool = True, budget: float = INDEX_BUDGET_S,
                     refresh: bool = False) -> dict[str, Any]:
        """Enable, extend, or delete a course's local materials index."""
        course_id = self.cfg.require_enabled(course_id)

        if not enable:
            with index.connect() as conn:
                removed = index.clear_course(conn, course_id)
            enabled = [cid for cid in self.cfg.indexed_course_ids if cid != course_id]
            self.cfg.set("index_enabled", enabled)
            self.cfg.save()
            return {
                "course_id": course_id,
                "enabled": False,
                "removed": removed,
                "message": f"Deleted the local index for {self.cfg.nickname(course_id)} ({removed} items).",
                **self.stamp(),
            }

        if course_id not in self.cfg.indexed_course_ids:
            self.cfg.set("index_enabled", [*self.cfg.indexed_course_ids, course_id])
            self.cfg.save()

        warnings: list[str] = []
        deadline = time.monotonic() + budget
        with index.connect() as conn:
            discovered = self._discover_materials(conn, course_id, warnings, refresh=refresh)
            # An explicit refresh is a student saying "try again", so a page that 503'd
            # last time is re-requested rather than left failed until Canvas happens to
            # bump its updated_at.
            done, failed, capped = self._extract_pending(conn, course_id, deadline, retry_failed=refresh)
            stats = index.course_stats(conn, course_id)
            still_failing = index.outstanding_failures(conn, course_id)
        if capped:
            warnings.append(
                f"This course has reached the {index.MAX_COURSE_CHARS // (1024 * 1024)} MB local index limit; "
                "the remaining files were left unindexed."
            )

        payload = {
            "course_id": course_id,
            "course": self.cfg.nickname(course_id),
            "enabled": True,
            "discovered": discovered,
            "indexed": stats.get("indexed", 0),
            "pending": stats.get("pending", 0),
            "skipped": stats.get("skipped", 0),
            # The outstanding total, not this pass's: "failed: 0" while a document is
            # still broken is how a student concludes their index is complete.
            "failed": len(still_failing),
            "failed_this_pass": failed,
            "next": "Call index_course again to continue." if stats.get("pending") else None,
            **self.stamp(warnings),
        }
        if still_failing:
            warnings.append(
                f"{len(still_failing)} material(s) could not be read and are not searchable: "
                + ", ".join(still_failing[:5])
                + (" and others" if len(still_failing) > 5 else "")
                + ". Call index_course again to retry them."
            )
            payload.update(self.stamp(warnings))
        payload["message"] = (
            f"Indexed {done} item(s) this pass; {stats.get('indexed', 0)} ready, {stats.get('pending', 0)} left."
        )
        return shrink(payload, BUDGETS["index_course"])

    def _discover_materials(self, conn: sqlite3.Connection, course_id: str, warnings: list[str], *,
                            refresh: bool) -> int:
        """Record every material in a course as pending, without downloading anything yet.

        A listing that succeeded is authoritative about what exists, so anything it does
        not mention has been removed and is tombstoned. A listing that *failed* says
        nothing, so nothing is removed on its account — deleting a course's materials
        because Canvas had a bad minute is a far worse error than keeping one stale page.
        """
        count = 0
        seen: dict[str, set[str]] = {}
        try:
            course = self.canvas.course(course_id, refresh=refresh)
            if course.get("syllabus_body"):
                index.upsert_material(
                    conn, course_id=course_id, kind="syllabus", canvas_id=course_id, title="Syllabus",
                    html_url=f"{self.canvas.base_url}/courses/{course_id}/assignments/syllabus",
                    source_updated_at=str(course.get("updated_at") or ""),
                )
                count += 1
            seen["syllabus"] = {course_id} if course.get("syllabus_body") else set()
        except CanvasError:
            warnings.append("The syllabus could not be read for this course.")

        module_lookup: dict[str, tuple[str, int, int]] = {}
        try:
            for position, module in enumerate(self.canvas.modules(course_id, refresh=refresh)):
                module_name = str(module.get("name") or "")
                for item_position, item in enumerate(module.get("items") or []):
                    if isinstance(item, dict) and item.get("content_id"):
                        module_lookup[str(item["content_id"])] = (module_name, position, item_position)
        except CanvasError:
            warnings.append("Module structure could not be read; materials will not be grouped by week.")

        try:
            found: set[str] = set()
            for page in self.canvas.pages(course_id, refresh=refresh):
                slug = str(page.get("url") or "")
                index.upsert_material(
                    conn, course_id=course_id, kind="page", canvas_id=slug,
                    title=str(page.get("title") or "Untitled"),
                    html_url=str(page.get("html_url") or ""),
                    source_updated_at=str(page.get("updated_at") or ""),
                )
                found.add(slug)
                count += 1
            seen["page"] = found
        except CanvasError:
            warnings.append("Course pages could not be read.")

        try:
            found = set()
            for record in self.canvas.files(course_id, refresh=refresh):
                summary = materials.file_summary(record)
                if not summary["canvas_id"]:
                    continue
                module_name, module_position, item_position = module_lookup.get(
                    summary["canvas_id"], ("", None, None)
                )
                index.upsert_material(
                    conn, course_id=course_id, kind="file", canvas_id=summary["canvas_id"],
                    title=summary["title"], module_name=module_name or None,
                    module_position=module_position, item_position=item_position,
                    html_url=summary["html_url"], content_type=summary["content_type"],
                    size_bytes=summary["size_bytes"], source_updated_at=summary["source_updated_at"],
                )
                found.add(summary["canvas_id"])
                count += 1
            seen["file"] = found
        except CanvasError:
            warnings.append(
                "This course does not share its file list with students; only pages and the syllabus were indexed."
            )

        for kind, present in seen.items():
            removed = index.tombstone_missing(conn, course_id, kind, present)
            if removed:
                warnings.append(
                    f"{removed} {kind}(s) were removed from bCourses since the last index and have been dropped."
                )
        conn.commit()
        return count

    def _extract_pending(self, conn: sqlite3.Connection, course_id: str, deadline: float, *,
                         retry_failed: bool = False) -> tuple[int, int, bool]:
        """Extract pending materials until the time or size budget runs out.

        Returns ``(indexed, failed, capped)``. The size cap is per course rather than
        per file: a hundred readable PDFs are as capable of filling a laptop as one
        pathological one.
        """
        done = 0
        failed = 0
        stored = index.course_chars(conn, course_id)

        for row in index.pending(conn, course_id, retry_failed=retry_failed):
            if time.monotonic() > deadline:
                break
            if stored >= index.MAX_COURSE_CHARS:
                return done, failed, True
            material_id = int(row["id"])
            kind = str(row["kind"])
            title = str(row["title"])
            try:
                extraction = self._extract_one(course_id, kind, row)
            except (CanvasError, materials.MaterialError) as exc:
                index.mark(conn, material_id, "failed", str(exc)[:200])
                failed += 1
                continue
            if extraction is None or extraction.status != "indexed":
                note = (extraction.note if extraction else "no content") or "no content"
                index.mark(conn, material_id, "skipped", note)
                continue
            chunks = materials.chunk_pages(extraction.pages, slides=_is_slides(title, str(row["content_type"] or "")))
            stored += index.store_chunks(conn, material_id, title, chunks, page_count=extraction.page_count,
                                         truncated=extraction.truncated)
            done += 1
        return done, failed, stored >= index.MAX_COURSE_CHARS

    def _extract_one(self, course_id: str, kind: str, row: sqlite3.Row) -> materials.Extraction | None:
        """Fetch and extract one material."""
        if kind == "syllabus":
            course = self.canvas.course(course_id)
            text = materials.html_to_text(str(course.get("syllabus_body") or ""))
            return materials.Extraction(pages=[text], page_count=1, char_count=len(text)) if text else None
        if kind == "page":
            page = self.canvas.page(course_id, str(row["canvas_id"]))
            text = materials.html_to_text(str(page.get("body") or ""))
            return materials.Extraction(pages=[text], page_count=1, char_count=len(text)) if text else None
        if kind == "file":
            title = str(row["title"])
            content_type = str(row["content_type"] or "")
            reason = materials.unsupported_reason(title, content_type)
            if reason:
                return materials.Extraction(status="skipped", note=reason)
            size = int(row["size_bytes"] or 0)
            if size and size > materials.MAX_DOWNLOAD_BYTES:
                return materials.Extraction(
                    status="skipped", note=f"file is {materials.human_size(size)}, over the extraction limit"
                )
            record = self.canvas.file(str(row["canvas_id"]))
            url = str(record.get("url") or "")
            if not url:
                return materials.Extraction(status="skipped", note="bCourses did not provide a download link")
            body, content, _ = materials.download(url, token=None)
            return materials.extract(body, title, content or content_type)
        return None

    def read_material(self, material_id: int, *, page: int | None = None, cursor: int = 0) -> str:
        """Return a material's text as Markdown with page markers.

        ``cursor`` is a character offset into the document, not a chunk index, so a
        single slide longer than the response budget is still readable: every call makes
        progress and every character is reachable.
        """
        with index.connect(create=False) as conn:
            row = index.get_material(conn, int(material_id))
            if row is None:
                raise ServiceError(
                    f"No material {material_id} is indexed. Call find_materials first to get a material_id."
                )
            if not self.cfg.is_enabled(str(row["course_id"])):
                raise ServiceError("That material belongs to a course you have not enabled.")
            status = str(row["status"])
            title = str(row["title"])
            if status != "indexed":
                note = str(row["status_note"] or "not extracted yet")
                return f"# {title}\n\n_Not readable: {note}._\n\nOpen it in bCourses: {row['html_url'] or 'bCourses'}"
            chunks = index.material_text(conn, int(material_id), page)

        if not chunks:
            return f"# {title}\n\n_No text on that page._"

        body, page_at = _render_material(chunks, paged=str(row["kind"]) == "file")
        cursor = max(0, int(cursor))
        if cursor >= len(body):
            return f"# {title}\n\n_Nothing left to read at cursor {cursor}._"

        heading = f"# {title}"
        if cursor:
            heading += f"\n\n_Continued from character {cursor}"
            resumed = page_at(cursor)
            if resumed is not None:
                heading += f", page {resumed}"
            heading += "._"

        room = BUDGETS["read_material"] - len(heading) - _CONTINUATION_ALLOWANCE
        window = body[cursor : cursor + max(room, 1)]
        if cursor + len(window) < len(body):
            # Break on a line so a page marker or sentence is not cut in half.
            split = window.rfind("\n")
            if split > len(window) // 2:
                window = window[:split]

        text = f"{heading}\n{window.rstrip()}"
        remaining = len(body) - (cursor + len(window))
        if remaining > 0:
            text += (
                f"\n\n_Continues. Call read_material again with cursor={cursor + len(window)} "
                f"for the rest ({remaining} characters left)._"
            )
        return text

    # -- study sessions ----------------------------------------------------

    def study_session(self, course_id: str, topic: str, *, mode: str = "tutor",
                      assignment_id: str | None = None) -> dict[str, Any]:
        """Assemble a tutoring package for one course and topic."""
        course_id = self.cfg.require_enabled(course_id)
        package = self.build_package(course_id, topic, mode=mode, assignment_id=assignment_id)
        payload = {**package.to_dict(), "course_id": course_id, **self.stamp()}
        # The assignment description and rubric live inside `facts`, where `shrink`
        # cannot see them: it only drops top-level list items. Trim them first, worst
        # offender at a time, so the rules and evidence survive.
        _trim_facts(payload, BUDGETS["prepare_study_session"])
        return shrink(payload, BUDGETS["prepare_study_session"])

    def build_package(self, course_id: str, topic: str, *, mode: str = "tutor",
                      assignment_id: str | None = None) -> pedagogy.Package:
        """Gather evidence, related work, and the course AI policy into one package."""
        notes: list[str] = []
        evidence = self.evidence_for(course_id, topic, notes)
        facts: dict[str, Any] = {}
        related: list[dict[str, Any]] = []

        if assignment_id:
            try:
                detail = self.assignment(course_id, assignment_id, max_chars=2500)
            except (ServiceError, CanvasError) as exc:
                notes.append(f"The assignment could not be read: {exc}")
            else:
                facts = {
                    "assignment": detail.get("title"),
                    "due": detail.get("due_human"),
                    "points": detail.get("points"),
                    "weight_pct": detail.get("weight_pct"),
                    "est_hours": detail.get("est_hours"),
                    "start_by": detail.get("start_by"),
                    "status": (detail.get("submission") or {}).get("state"),
                    "description": detail.get("description"),
                    "rubric": detail.get("rubric"),
                }
        else:
            try:
                upcoming = self.deadlines(window="2weeks", course_id=course_id, limit=5)
                related = [
                    {"title": item["title"], "due_human": item["due_human"], "weight_pct": item.get("weight_pct")}
                    for item in upcoming.get("items", [])
                ]
            except (ServiceError, CanvasError):
                notes.append("Upcoming work for this course could not be read.")

        return pedagogy.build_package(
            mode,
            course=self.cfg.nickname(course_id),
            topic=topic,
            evidence=evidence,
            related_assignments=related,
            facts=facts,
            ai_policy=self.ai_policy(course_id),
            notes=notes,
        )

    def evidence_for(self, course_id: str, topic: str, notes: list[str]) -> list[pedagogy.Evidence]:
        """Return citable excerpts about a topic from the student's own materials."""
        if course_id not in self._indexed_course_ids():
            notes.append(
                "This course is not indexed, so there are no excerpts from its slides or readings. "
                "Call index_course to enable that."
            )
            return []
        with index.connect() as conn:
            hits = index.search(conn, course_id, topic, limit=pedagogy.MAX_EVIDENCE)
            stats = index.course_stats(conn, course_id)
        if stats.get("pending"):
            notes.append(f"{stats['pending']} file(s) in this course are not extracted yet.")
        return [
            pedagogy.Evidence(
                title=hit.title,
                excerpt=pedagogy.trim_excerpt(hit.snippet.replace("[", "").replace("]", "")),
                cite=hit.to_dict()["cite"],
                url=hit.html_url,
            )
            for hit in hits
        ]

    def ai_policy(self, course_id: str) -> dict[str, str] | None:
        """Return the course's stated AI policy from its syllabus, when it has one."""
        try:
            course = self.canvas.course(course_id)
        except CanvasError:
            return None
        text = materials.html_to_text(str(course.get("syllabus_body") or ""))
        return pedagogy.find_ai_policy(text, cite=f"({self.cfg.nickname(course_id)} syllabus)")

    # -- catalog and schedule ----------------------------------------------

    def search_catalog(self, *, query: str = "", subject: str | None = None, level: str | None = None,
                       units: str | None = None, offered_term: str | None = None,
                       limit: int = 10) -> dict[str, Any]:
        """Search the Berkeley catalog, optionally restricted to a term's offerings."""
        catalog.ensure_built()
        message = catalog.maybe_update(enabled=self.cfg.data_updates)
        with catalog.connect() as conn:
            result = catalog.search(
                conn, query=query, subject=subject, level=level, units=units,
                offered_term=offered_term, limit=limit,
            )
        warnings = [message] if message else []
        if offered_term and offered_term not in result.get("terms_known", []):
            warnings.append(
                f"{offered_term} is not in the offerings snapshot. The Registrar posts one term ahead at most."
            )
        result.update(self.stamp(warnings))
        result["advice_note"] = (
            "These are fit-based matches from a catalog snapshot, not official advising. "
            "Prefer courses with known offerings, and check requirements with your advisor."
        )
        # Shorten the gists before letting `shrink` drop whole courses: a student
        # scanning for something to take is worse served by nine results than by ten
        # slightly terser ones.
        result = catalog.fit_previews(result, BUDGETS["search_catalog"])
        return shrink(result, BUDGETS["search_catalog"])

    def catalog_course(self, subject: str, number: str) -> dict[str, Any]:
        """Return one catalog course in full."""
        catalog.ensure_built()
        catalog.maybe_update(enabled=self.cfg.data_updates)
        with catalog.connect() as conn:
            course = catalog.details(conn, subject, number)
            known = catalog.terms_known(conn)
        if course is None:
            raise ServiceError(
                f"{subject.upper()} {number} is not in the catalog snapshot. Check the subject code with "
                "search_catalog, or try check_offering for live section data."
            )
        payload = {"course": course, "terms_known": known, **self.stamp()}
        if "offered_terms" not in course:
            payload["offerings_note"] = (
                "No scheduled sections are known for this course in the terms covered by the snapshot."
            )
        return shrink(payload, BUDGETS["get_catalog_course"])

    def _schedule_terms(self) -> list[schedule.Facet]:
        """Return the schedule's term list, cached for a day.

        The term list changes when the Registrar posts a new semester, so re-reading it
        on every lookup would spend a request on an answer that is stable for months.
        Caching it keeps the common path to a single request against the schedule site.
        """
        cached = self.cache.get("schedule:terms")
        if cached is not None:
            return cached
        try:
            terms = schedule.list_terms()
        except schedule.ScheduleError as exc:
            raise ServiceError(str(exc)) from exc
        self.cache.set("schedule:terms", terms, OFFERING_CACHE_S)
        return terms

    def check_offering(self, course_code: str, term: str | None = None) -> dict[str, Any]:
        """Ask classes.berkeley.edu for a course's live sections. One request, cached a day."""
        parsed = catalog.parse_course_code(course_code)
        if parsed is None:
            raise ServiceError(f"{course_code!r} does not look like a course code. Try something like 'STAT 156'.")
        wanted = f"{parsed[0]} {parsed[1]}"

        key = f"offering:{wanted}:{term or 'newest'}"
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        terms = self._schedule_terms()

        if term:
            match = next((t for t in terms if t.name.lower() == term.strip().lower()), None)
            if match is None:
                available = ", ".join(t.name for t in schedule.sorted_terms(terms)[:4])
                payload = {
                    "course": wanted,
                    "term": term,
                    "sections": [],
                    "note": f"{term} is not posted on the class schedule yet. Terms available now: {available}.",
                    **self.stamp(),
                }
                self.cache.set(key, payload, OFFERING_CACHE_S)
                return payload
            chosen = match
        else:
            chosen = schedule.newest_term(terms)
            if chosen is None:
                raise ServiceError("The Berkeley class schedule did not list any terms.")

        try:
            sections = schedule.find_sections(wanted, chosen.facet_id)
        except schedule.ScheduleError as exc:
            raise ServiceError(str(exc)) from exc

        payload: dict[str, Any] = {
            "course": wanted,
            "term": chosen.name,
            "sections": [section.to_dict() for section in sections],
            "fetched_at": iso(self.now()),
            "source": "classes.berkeley.edu",
            **self.stamp(),
        }
        if not sections:
            payload["note"] = f"{wanted} has no scheduled sections in {chosen.name}."
        payload["terms_available"] = [t.name for t in schedule.sorted_terms(terms)[:4]]
        payload = shrink(payload, BUDGETS["check_offering"])
        self.cache.set(key, payload, OFFERING_CACHE_S)
        return payload


# -- helpers -----------------------------------------------------------------


def _trim_facts(payload: dict[str, Any], budget: int, *, floor: int = 400) -> None:
    """Shrink the nested assignment prose in a study package until it fits its budget."""
    facts = payload.get("facts")
    if not isinstance(facts, dict):
        return

    while encoded_size(payload) > budget:
        rubric = facts.get("rubric")
        description = str(facts.get("description") or "")
        if isinstance(rubric, list) and len(rubric) > 3:
            rubric.pop()
            continue
        if len(description) > floor:
            facts["description"] = description[: max(floor, int(len(description) * 0.8))].rstrip() + "..."
            continue
        return


def _render_material(chunks: list[Any], *, paged: bool) -> tuple[str, Any]:
    """Render a material's chunks once, and return a way to look up the page at an offset."""
    parts: list[str] = []
    marks: list[tuple[int, int]] = []
    length = 0
    current_page: int | None = None

    for chunk in chunks:
        piece = ""
        if paged and chunk["page_start"] != current_page:
            current_page = int(chunk["page_start"] or 0)
            piece += f"\n--- p. {current_page} ---\n"
        piece += str(chunk["text"]) + "\n"
        if current_page is not None:
            marks.append((length, current_page))
        parts.append(piece)
        length += len(piece)

    body = "".join(parts)

    def page_at(offset: int) -> int | None:
        """Return the page a character offset falls on, for a continuation header."""
        found = None
        for position, number in marks:
            if position <= offset:
                found = number
            else:
                break
        return found

    return body, page_at


def _rubric(assignment: dict[str, Any]) -> list[dict[str, Any]]:
    """Reduce a Canvas rubric to criterion, points, and description."""
    rows = []
    for criterion in assignment.get("rubric") or []:
        if not isinstance(criterion, dict):
            continue
        rows.append({
            "criterion": str(criterion.get("description") or "Untitled"),
            "points": _as_float(criterion.get("points")),
            "detail": materials.html_to_text(str(criterion.get("long_description") or ""))[:300] or None,
        })
    return [{key: value for key, value in row.items() if value is not None} for row in rows]


def _excerpt_around(text: str, needle: str, width: int = 400) -> str | None:
    """Return the passage of a document around the first match of a phrase."""
    lowered = text.lower()
    position = lowered.find(needle)
    if position < 0:
        words = [word for word in needle.split() if len(word) > 3]
        for word in words:
            position = lowered.find(word)
            if position >= 0:
                break
        else:
            return None
    start = max(0, position - width // 3)
    return " ".join(text[start : start + width].split())


def _is_slides(title: str, content_type: str) -> bool:
    """Return whether a file should be chunked slide-style rather than page-style."""
    lowered = title.lower()
    return lowered.endswith(".pptx") or "presentation" in content_type or "slide" in lowered


def _as_float(value: object) -> float | None:
    """Coerce a numeric field to ``float``."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    """Coerce a field to a non-empty string, or ``None``."""
    text = str(value or "").strip()
    return text or None
