"""The deadline ranking rules, pinned as a golden table.

`agenda` is pure arithmetic over Canvas dictionaries, so these tests are the contract
for what a student is told to work on. If a rule changes, this file changes with it —
deliberately.
"""

from __future__ import annotations

from datetime import date, timedelta
from zoneinfo import ZoneInfo

import pytest

from openmind import agenda
from tests.conftest import GROUPS_1001, GROUPS_1002, NOW_UTC, TZ, canvas_dt

REFERENCE = NOW_UTC.astimezone(ZoneInfo(TZ))  # Friday 2026-09-04, 15:00 Berkeley


@pytest.fixture
def weights() -> agenda.WeightTable:
    return agenda.build_weight_table(GROUPS_1001, apply_group_weights=True)


def build(raw: dict, weights: agenda.WeightTable, course: str = "Causal Inference") -> agenda.AgendaItem:
    item = agenda.build_item(
        raw, course_id="1001", course_name=course, weights=weights, tz=TZ, reference=REFERENCE, capacity=2.0
    )
    assert item is not None
    return item


def planner(title: str, days: float, points: float | None = 20, *, plannable_type: str = "assignment",
            plannable_id: int = 201, submissions: dict | None = None, **plannable) -> dict:
    return {
        "course_id": 1001,
        "plannable_id": plannable_id,
        "plannable_type": plannable_type,
        "plannable_date": canvas_dt(days),
        "plannable": {"id": plannable_id, "title": title, "due_at": canvas_dt(days),
                      "points_possible": points, **plannable},
        "submissions": submissions or {},
    }


# -- weights -------------------------------------------------------------------


def test_group_weights_are_split_across_a_group_by_points(weights: agenda.WeightTable):
    """Problem Sets is 40% over two 20-point sets, so each set is 20% of the grade."""
    assert weights.basis == "groups"
    assert weights.weight_of("201") == pytest.approx(20.0)
    assert weights.weight_of("202") == pytest.approx(20.0)
    assert weights.weight_of("203") == pytest.approx(30.0)
    assert weights.weight_of("204") == pytest.approx(30.0)


def test_zero_point_and_omitted_assignments_take_no_weight(weights: agenda.WeightTable):
    assert weights.weight_of("209") is None  # 0 points
    assert weights.weight_of("205") is None  # omit_from_final_grade


def test_drop_rules_are_reported_rather_than_modelled(weights: agenda.WeightTable):
    assert weights.note is not None
    assert "drops some scores" in weights.note


def test_quiz_ids_map_back_to_their_assignment(weights: agenda.WeightTable):
    assert weights.quiz_to_assignment["5001"] == "203"


def test_unweighted_courses_use_points_out_of_the_course_total():
    table = agenda.build_weight_table(GROUPS_1002, apply_group_weights=False)
    assert table.basis == "points"
    assert table.weight_of("301") == pytest.approx(10.0)
    assert table.weight_of("302") == pytest.approx(90.0)


def test_weights_are_unknown_when_there_is_nothing_to_divide():
    table = agenda.build_weight_table([{"name": "Empty", "group_weight": 100, "assignments": []}],
                                      apply_group_weights=True)
    assert table.basis == "groups"
    assert table.weight_of("1") is None


# -- status --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("flags", "days", "submission_types", "expected"),
    [
        ({"excused": True, "graded": True}, -1, ["online_upload"], "excused"),
        ({"graded": True}, -1, ["online_upload"], "graded"),
        ({"submitted": True}, -1, ["online_upload"], "submitted"),
        ({"submitted": True, "late": True}, -1, ["online_upload"], "submitted_late"),
        ({"missing": True}, 3, ["online_upload"], "missing"),
        ({}, -1, ["online_upload"], "missing"),
        ({}, -1, ["on_paper"], "past_due_offline"),
        ({}, 3, ["online_upload"], "unsubmitted"),
    ],
)
def test_status_takes_the_first_matching_signal(flags, days, submission_types, expected, weights):
    item = build(planner("Thing", days, submissions=flags, submission_types=submission_types), weights)
    assert item.status == expected


def test_a_locked_past_due_item_is_marked_locked(weights: agenda.WeightTable):
    raw = planner("Problem Set 4", -2, submission_types=["online_upload"])
    raw["plannable"]["lock_at"] = canvas_dt(-1)
    assert build(raw, weights).status == "missing_locked"


def test_an_item_without_a_due_date_is_undated(weights: agenda.WeightTable):
    raw = planner("Course survey", 0)
    raw["plannable_date"] = None
    raw["plannable"]["due_at"] = None
    assert build(raw, weights).status == "undated"


# -- estimates -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("title", "plannable_type", "points", "expected"),
    [
        ("Final Exam", "quiz", 100, 8.0),
        ("Midterm 1", "quiz", 100, 4.0),
        ("Weekly check-in", "quiz", 2, 0.5),
        ("Discussion 4", "discussion_topic", 5, 0.75),
        ("Final Project", "assignment", 90, 15.0),
        ("Midterm essay", "assignment", 50, 4.0),
        ("Problem Set 3", "assignment", 20, 2.5),
        ("Reading response 2", "assignment", 10, 1.5),
        ("Reading: Chapter 4", "assignment", 5, 0.75),
        ("Course survey", "assignment", 1, 0.25),
        ("Widget", "assignment", 40, 4.0),
    ],
)
def test_hour_estimates_follow_type_then_keyword_then_points(title, plannable_type, points, expected):
    assert agenda.estimate_hours(title, plannable_type, points, None).hours == pytest.approx(expected)


def test_heavy_weight_raises_the_floor_on_a_plain_title():
    """A 25%-of-grade "Assignment 2" is not a two-hour job however dull its name."""
    plain = agenda.estimate_hours("Assignment 2", "assignment", 20, None)
    heavy = agenda.estimate_hours("Assignment 2", "assignment", 20, 25.0)
    medium = agenda.estimate_hours("Assignment 2", "assignment", 20, 12.0)
    assert plain.hours == 2.0
    assert heavy.hours == 6.0
    assert medium.hours == 3.0


def test_confidence_is_low_only_when_falling_through_to_points():
    assert agenda.estimate_hours("Problem Set 1", "assignment", 20, None).confidence == "medium"
    assert agenda.estimate_hours("Widget", "assignment", 40, None).confidence == "low"


# -- start-by ------------------------------------------------------------------


def test_start_by_backs_off_from_the_due_date_by_the_days_of_work_needed():
    due = REFERENCE + timedelta(days=6)
    day, overdue_start = agenda.start_by(due, 6.0, REFERENCE, 2.0)
    assert day == (due.date() - timedelta(days=2))
    assert overdue_start is False


def test_start_by_never_precedes_today_but_says_when_it_should_have():
    due = REFERENCE + timedelta(days=1)
    day, should_have_started = agenda.start_by(due, 15.0, REFERENCE, 2.0)
    assert day == REFERENCE.date()
    assert should_have_started is True


def test_quick_tasks_start_on_their_due_date():
    due = REFERENCE + timedelta(days=4)
    day, _ = agenda.start_by(due, 0.5, REFERENCE, 2.0)
    assert day == due.date()


# -- priority ------------------------------------------------------------------


def test_golden_priorities(weights: agenda.WeightTable):
    """One table, one row per rule, so a regression names itself."""
    cases = [
        ("Problem Set 3", 0, 201, "HIGH", "due today"),
        ("Problem Set 3", 2, 201, "HIGH", "due in 2 days"),
        ("Midterm 1", 6, 203, "HIGH", "worth 30% of grade"),
        ("Reading: Chapter 4", 4, 999, "MED", "due in 4 days"),
        ("Course survey", 12, 998, "LOW", "due in 12 days"),
    ]
    for title, days, plannable_id, expected_priority, expected_reason in cases:
        item = build(planner(title, days, plannable_id=plannable_id), weights)
        assert item.priority == expected_priority, f"{title}: {item.priority} ({item.reason})"
        assert expected_reason in item.reason, f"{title}: {item.reason}"


def test_overdue_work_is_high_and_says_why(weights: agenda.WeightTable):
    item = build(planner("Problem Set 4", -3, plannable_id=202, submissions={"missing": True}), weights)
    assert item.priority == "HIGH"
    assert item.reason == "past due and not submitted"


def test_a_long_job_due_next_week_is_bumped_out_of_low(weights: agenda.WeightTable):
    """A 15-hour project needs 8 days at 2h/day, so on day 7 it is already late to start."""
    item = build(planner("Final Project", 7, points=50, plannable_id=997), weights)
    assert item.est_hours == 15.0
    assert item.start_now is True
    assert item.priority == "MED"
    assert "start now" in item.reason


def test_an_already_high_item_still_reports_start_now(weights: agenda.WeightTable):
    """The label cannot go higher, so the urgency shows up as a field instead."""
    item = build(planner("Final Project", 6, points=90, plannable_id=996), weights)
    assert item.priority == "HIGH"
    assert item.start_now is True
    assert item.to_dict(REFERENCE)["start_note"] == "start now"


def test_the_start_now_bump_never_lowers_a_label(weights: agenda.WeightTable):
    for days in range(0, 30):
        for title in ("Course survey", "Problem Set 3", "Final Project"):
            candidate = build(planner(title, days, plannable_id=996), weights)
            base = agenda._prioritise(candidate.status, candidate.days, False, None, None, candidate.est_hours, False)
            assert agenda._LABEL_RANK[candidate.priority] <= agenda._LABEL_RANK[base[0]]


def test_heavy_points_stand_in_for_an_unknown_weight():
    """Without group weights, a 100-point item still has to outrank a 5-point one."""
    empty = agenda.WeightTable(median_points=10.0)
    item = agenda.build_item(
        planner("Term Paper", 10, points=100, plannable_id=900), course_id="1001", course_name="X",
        weights=empty, tz=TZ, reference=REFERENCE, capacity=2.0,
    )
    assert item is not None
    assert item.weight_pct is None
    assert item.priority == "HIGH"
    assert "100 pts; weight unknown" in item.reason
    assert item.weight_note == "100 pts; weight unknown"


def test_completed_work_is_never_urgent(weights: agenda.WeightTable):
    item = build(planner("Problem Set 3", 0, submissions={"submitted": True}), weights)
    assert item.priority == "LOW"
    assert item.start_now is False


# -- ranges, ordering, and counts ----------------------------------------------


def test_this_week_runs_through_sunday():
    start, end = agenda.resolve_range("this_week", REFERENCE)
    assert start == date(2026, 9, 4)
    assert end == date(2026, 9, 6)
    assert end.weekday() == 6


@pytest.mark.parametrize(
    ("name", "expected_days"), [("today", 0), ("next_7_days", 7), ("2weeks", 14), ("month", 30)]
)
def test_ranges_span_the_advertised_length(name: str, expected_days: int):
    start, end = agenda.resolve_range(name, REFERENCE)
    assert (end - start).days == expected_days


def test_items_are_ordered_by_urgency_then_by_when_to_start(weights: agenda.WeightTable):
    items = [
        build(planner("Course survey", 20, plannable_id=990), weights),
        build(planner("Problem Set 3", 0, plannable_id=201), weights),
        build(planner("Midterm 1", 6, plannable_id=203), weights),
        build(planner("Reading: Chapter 4", 4, plannable_id=991), weights),
    ]
    ordered = [item.title for item in agenda.sort_items(items)]
    assert ordered[0] == "Problem Set 3"
    assert ordered.index("Midterm 1") < ordered.index("Course survey")


def test_overdue_puts_still_submittable_work_first(weights: agenda.WeightTable):
    locked = planner("Locked set", -5, plannable_id=980)
    locked["plannable"]["lock_at"] = canvas_dt(-4)
    items = [build(locked, weights), build(planner("Open set", -2, plannable_id=981), weights)]
    ordered = agenda.sort_overdue(items)
    assert ordered[0].title == "Open set"


def test_counts_summarise_without_the_host_having_to_add_up(weights: agenda.WeightTable):
    upcoming = [build(planner("Problem Set 3", 0, plannable_id=201), weights)]
    overdue = [build(planner("Problem Set 4", -3, plannable_id=202, submissions={"missing": True}), weights)]
    totals = agenda.counts(upcoming, overdue)
    assert totals == {"total": 2, "overdue": 1, "high": 1, "med": 0, "low": 0, "est_hours": 6.0}


def test_calendar_events_and_notes_are_not_agenda_items(weights: agenda.WeightTable):
    raw = planner("Office hours", 1, plannable_type="calendar_event")
    assert agenda.build_item(raw, course_id="1001", course_name="X", weights=weights, tz=TZ,
                             reference=REFERENCE, capacity=2.0) is None


def test_the_assignments_source_produces_the_same_shape(weights: agenda.WeightTable):
    raw = {
        "id": 201, "name": "Problem Set 3", "due_at": canvas_dt(0), "points_possible": 20,
        "submission_types": ["online_upload"], "submission": {"workflow_state": "unsubmitted"},
        "html_url": "https://bcourses.berkeley.edu/courses/1001/assignments/201",
    }
    item = agenda.build_item_from_assignment(
        raw, course_id="1001", course_name="Causal Inference", weights=weights, tz=TZ,
        reference=REFERENCE, capacity=2.0,
    )
    assert item is not None
    assert item.priority == "HIGH"
    assert item.weight_pct == pytest.approx(20.0)
    assert item.to_dict(REFERENCE)["due_human"] == "Fri Sep 4, 11:59 PM"


def test_rendered_items_carry_both_machine_and_human_dates(weights: agenda.WeightTable):
    payload = build(planner("Problem Set 3", 0, plannable_id=201), weights).to_dict(REFERENCE)
    assert payload["due_human"] == "Fri Sep 4, 11:59 PM"
    assert payload["due_local"].startswith("2026-09-04T23:59")
    assert payload["days"] == 0
    assert payload["weight_pct"] == 20.0
    assert payload["start_by_human"].startswith("Fri Sep 4")
