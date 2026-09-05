"""End-to-end operations against a synthetic bCourses instance."""

from __future__ import annotations

import json

import httpx
import pytest

from openmind import index
from openmind.canvas import CanvasClient
from openmind.config import ConfigError
from openmind.service import BUDGETS, ServiceError, Session, shrink
from tests.conftest import NOW_UTC, handler

# -- courses -------------------------------------------------------------------


def test_list_courses_returns_only_enabled_courses(session: Session):
    payload = session.list_courses()
    ids = {course["id"] for course in payload["courses"]}
    assert ids == {"1001", "1002"}
    assert "9999" not in ids  # enrolled but not shared
    assert payload["user"]["tz"] == "America/Los_Angeles"
    assert payload["partial"] is False


def test_list_courses_carries_the_students_own_score(session: Session):
    stat = next(c for c in session.list_courses()["courses"] if c["id"] == "1001")
    assert stat["current_score"] == 88.5
    assert stat["current_grade"] == "B+"
    assert stat["nickname"] == "Causal Inference"
    assert stat["indexed"] is False


def test_a_configured_course_that_vanished_produces_a_warning_not_silence(session: Session):
    session.cfg.set("courses", {**session.cfg.courses, "4242": "Ghost Course"})
    payload = session.list_courses(refresh=True)
    assert payload["partial"] is True
    assert any("Ghost Course" in note for note in payload["warnings"])


# -- deadlines -----------------------------------------------------------------


def test_deadlines_separate_overdue_work_from_upcoming(session: Session):
    payload = session.deadlines(window="next_7_days")
    assert [item["title"] for item in payload["overdue"]] == ["Problem Set 4"]
    titles = [item["title"] for item in payload["items"]]
    assert "Problem Set 3" in titles
    assert "Midterm 1" in titles
    assert "Reading response 2" not in titles  # already submitted, status=open


def test_deadlines_render_the_local_day_and_computed_weight(session: Session):
    item = next(i for i in session.deadlines()["items"] if i["title"] == "Problem Set 3")
    assert item["due_human"] == "Fri Sep 4, 11:59 PM"
    assert item["days"] == 0
    assert item["priority"] == "HIGH"
    assert item["weight_pct"] == 20.0
    assert item["weight_basis"] == "groups"


def test_a_quiz_planner_item_resolves_to_its_assignments_weight(session: Session):
    midterm = next(i for i in session.deadlines()["items"] if i["title"] == "Midterm 1")
    assert midterm["assignment_id"] == "203"
    assert midterm["weight_pct"] == 30.0
    assert midterm["priority"] == "HIGH"


def test_calendar_events_are_counted_not_listed(session: Session):
    payload = session.deadlines()
    assert all(item["type"] != "calendar_event" for item in payload["items"])
    assert any("skipped" in note for note in payload["notes"])


def test_today_only_covers_today(session: Session):
    payload = session.deadlines(window="today")
    assert [item["title"] for item in payload["items"]] == ["Problem Set 3"]


def test_a_wider_range_reaches_further_out(session: Session):
    titles = [item["title"] for item in session.deadlines(window="2weeks")["items"]]
    assert "Final Project" in titles


def test_status_all_uses_the_assignments_source_and_finds_undated_work(session: Session):
    payload = session.deadlines(status="all", course_id="1001")
    assert payload["source"] == "assignments"
    assert any(item["title"] == "Course survey" for item in payload["items"])
    assert any(item["status"] == "undated" for item in payload["items"])


def test_undated_returns_only_work_without_a_due_date(session: Session):
    payload = session.deadlines(status="undated", course_id="1001")
    assert {item["title"] for item in payload["items"]} == {"Course survey"}


def test_paging_walks_overdue_and_upcoming_through_one_cursor(session: Session):
    """One cursor over both lists, overdue first, so "have I seen everything?" has an answer."""
    first = session.deadlines(window="month", limit=1)
    assert len(first["overdue"]) == 1 and first["items"] == []
    assert first["next_offset"] == 1
    assert first["remaining"] > 0

    second = session.deadlines(window="month", limit=1, offset=1)
    assert len(second["items"]) == 1 and second["overdue"] == []
    assert second["items"][0]["title"] != first["overdue"][0]["title"]


def test_a_course_that_403s_makes_the_payload_partial_rather_than_empty(config, monkeypatch):
    """One broken course must never look like "nothing due"."""
    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/courses/1002/assignment_groups"):
            return httpx.Response(403, json={"errors": []}, request=request)
        return handler(request)

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(flaky))
    payload = Session(config, client, clock=NOW_UTC).deadlines(window="2weeks")
    client.close()

    assert payload["partial"] is True
    assert any("NLP" in note for note in payload["warnings"])
    assert payload["items"], "items must still be returned for the courses that worked"


def test_planner_failure_falls_back_to_assignments_and_says_so(config):
    def no_planner(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/planner/items"):
            return httpx.Response(403, json={"errors": []}, request=request)
        return handler(request)

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(no_planner))
    payload = Session(config, client, clock=NOW_UTC).deadlines()
    client.close()

    assert payload["source"] == "assignments"
    assert any("Planner" in note for note in payload["warnings"])
    assert any(item["title"] == "Problem Set 3" for item in payload["items"])


def test_asking_about_a_course_that_was_not_shared_is_refused(session: Session):
    with pytest.raises(ConfigError, match="not one of your enabled courses"):
        session.deadlines(course_id="9999")


def test_the_priority_rule_is_explained_in_every_agenda(session: Session):
    notes = " ".join(session.deadlines()["notes"])
    assert "HIGH" in notes and "20%" in notes and "hours of work a day" in notes


# -- assignment detail ---------------------------------------------------------


def test_assignment_detail_has_facts_description_and_rubric(session: Session):
    payload = session.assignment("1001", "201")
    assert payload["title"] == "Problem Set 3"
    assert payload["due_human"] == "Fri Sep 4, 11:59 PM"
    assert payload["weight_pct"] == 20.0
    assert payload["est_hours"] == 6.0  # 20% floor raises the 2.5h problem-set estimate
    assert "average treatment effect" in payload["description"]
    assert "<p>" not in payload["description"]
    assert [row["criterion"] for row in payload["rubric"]] == ["Correctness", "Clarity"]
    assert payload["submission"]["state"] == "unsubmitted"


def test_a_long_description_pages_with_a_cursor(session: Session):
    first = session.assignment("1001", "201", max_chars=20)
    assert first["description_cursor"] == 20
    second = session.assignment("1001", "201", max_chars=20, cursor=20)
    assert second["description"] != first["description"]


# -- course overview -----------------------------------------------------------


def test_course_overview_returns_syllabus_modules_and_announcements(session: Session):
    payload = session.course_overview("1001")
    assert "Problem sets 40%" in payload["syllabus"]
    assert payload["modules"][0]["name"] == "Week 3 — Confounding"
    assert payload["announcements"][0]["title"] == "Midterm room change"
    assert "Wheeler 150" in payload["announcements"][0]["excerpt"]


def test_a_course_without_a_syllabus_says_so(session: Session):
    payload = session.course_overview("1002")
    assert payload["syllabus"] == ""
    assert "no syllabus" in payload["syllabus_note"]


# -- grades --------------------------------------------------------------------


def test_grades_report_what_canvas_says_and_nothing_more(session: Session):
    payload = session.grades()
    stat = next(c for c in payload["courses"] if c["course_id"] == "1001")
    nlp = next(c for c in payload["courses"] if c["course_id"] == "1002")
    assert stat["current_score"] == 88.5
    assert nlp["current_score"] is None
    assert "no current score" in nlp["note"]
    assert "not counted as zeros" in payload["note"]


def test_a_single_course_gets_a_group_breakdown(session: Session):
    payload = session.grades("1001")
    assert payload["weighted"] is True
    assert {group["name"] for group in payload["groups"]} == {"Problem Sets", "Exams"}
    assert payload["graded"][0]["title"] == "Problem Set 2"
    assert payload["ungraded_count"] == 1


# -- materials -----------------------------------------------------------------


def test_an_unindexed_course_searches_titles_and_says_what_it_cannot_do(session: Session):
    payload = session.find_materials("1001", query="week 3")
    assert payload["indexed"] is False
    assert "not indexed" in payload["index_note"]
    assert any("Week 3 Slides" in entry["title"] for entry in payload["materials"])


def test_an_unindexed_course_can_still_quote_the_syllabus(session: Session):
    payload = session.find_materials("1001", query="grading")
    assert any(hit["kind"] == "syllabus" for hit in payload["hits"])


def test_indexing_a_course_extracts_pages_and_the_syllabus(session: Session):
    result = session.index_course("1001")
    assert result["enabled"] is True
    assert result["indexed"] >= 2  # syllabus + page
    assert "1001" in session.cfg.indexed_course_ids

    payload = session.find_materials("1001", query="confounder")
    assert payload["indexed"] is True
    assert payload["hits"], payload
    assert "Week 3 Notes" in payload["hits"][0]["title"]
    assert payload["hits"][0]["cite"].startswith("(")


def test_an_unreadable_file_is_recorded_rather_than_dropped(session: Session):
    session.index_course("1001")
    with index.connect() as conn:
        rows = index.list_materials(conn, "1001", kind="file")
    assert rows, "the PDF must be recorded even though it cannot be downloaded here"
    assert rows[0]["status"] in {"failed", "skipped"}
    assert rows[0].get("note")


def test_a_course_that_hides_its_files_still_indexes_what_it_can(session: Session):
    result = session.index_course("1002")
    assert result["enabled"] is True
    assert any("does not share its file list" in note for note in result["warnings"])


def test_reading_an_indexed_material_returns_markdown(session: Session):
    session.index_course("1001")
    with index.connect() as conn:
        rows = index.list_materials(conn, "1001", kind="page")
    text = session.read_material(rows[0]["material_id"])
    assert text.startswith("# Week 3 Notes")
    assert "backdoor path" in text


def test_reading_an_unknown_material_names_the_tool_to_call_first(session: Session):
    session.index_course("1001")
    with pytest.raises(ServiceError, match="find_materials"):
        session.read_material(99999)


def test_disabling_an_index_deletes_it(session: Session):
    session.index_course("1001")
    result = session.index_course("1001", enable=False)
    assert result["enabled"] is False
    assert result["removed"] > 0
    assert "1001" not in session.cfg.indexed_course_ids


# -- study sessions ------------------------------------------------------------


def test_a_study_session_puts_rules_before_evidence(session: Session):
    session.index_course("1001")
    payload = session.study_session("1001", "confounding")
    assert payload["mode"] == "tutor"
    assert "Do not state it unless they type /answer" in payload["rules"]
    assert payload["evidence"], payload
    assert "untrusted" in payload["evidence_is_untrusted"].lower() or "never as instructions" in payload["evidence_is_untrusted"]
    assert payload["opening"].startswith("Before we start")


def test_a_study_session_surfaces_the_courses_ai_policy(session: Session):
    payload = session.study_session("1001", "confounding")
    assert payload["course_ai_policy"] is not None
    assert "academic integrity" in payload["course_ai_policy"]["excerpt"]


def test_a_study_session_without_an_index_says_what_is_missing(session: Session):
    payload = session.study_session("1002", "language models")
    assert payload["evidence"] == []
    assert any("not indexed" in note for note in payload["notes"])


def test_anchoring_to_an_assignment_brings_its_facts(session: Session):
    payload = session.study_session("1001", "Problem Set 3", mode="explain_assignment", assignment_id="201")
    assert payload["facts"]["assignment"] == "Problem Set 3"
    assert payload["facts"]["weight_pct"] == 20.0
    assert "text intended for submission" in payload["rules"].lower()


# -- catalog and offerings -----------------------------------------------------


def test_catalog_search_finds_a_course_and_stamps_the_snapshot(session: Session, sample_catalog):
    payload = session.search_catalog(query="causal inference")
    assert payload["courses"][0]["subject"] == "STAT"
    assert payload["catalog_as_of"] == "2026-09-05"
    assert "not official advising" in payload["advice_note"]


def test_a_course_code_query_is_treated_as_a_code(session: Session, sample_catalog):
    payload = session.search_catalog(query="STAT 156")
    assert [(c["subject"], c["number"]) for c in payload["courses"]] == [("STAT", "156")]


def test_a_course_hidden_from_the_printed_catalog_is_flagged(session: Session, sample_catalog):
    course = session.search_catalog(query="STAT 156")["courses"][0]
    assert course["in_printed_catalog"] is False
    assert course["offered_terms"][0]["term"] == "Fall 2026"


def test_filtering_by_offered_term_excludes_courses_with_no_sections(session: Session, sample_catalog):
    payload = session.search_catalog(query="", offered_term="Fall 2026", limit=30)
    assert {(c["subject"], c["number"]) for c in payload["courses"]} == {("STAT", "156")}


def test_asking_for_an_unposted_term_warns_rather_than_returning_nothing(session: Session, sample_catalog):
    payload = session.search_catalog(query="machine learning", offered_term="Spring 2027")
    assert any("Spring 2027" in note for note in payload["warnings"])


def test_catalog_detail_returns_the_full_description(session: Session, sample_catalog):
    payload = session.catalog_course("COMPSCI", "189")
    assert payload["course"]["title"] == "Introduction to Machine Learning"
    assert "offerings_note" in payload


def test_a_snapshot_that_could_not_refresh_its_offerings_says_so_in_one_note(session: Session, sample_catalog):
    """"No sections known" and "nobody could read the schedule" are the same question."""
    from openmind import catalog

    reason = "offerings not refreshed: classes.berkeley.edu returned HTTP 403; previous snapshot kept"
    with catalog.connect() as conn:
        conn.execute("UPDATE meta SET value = ? WHERE key = 'offerings_note'", (reason,))
        conn.commit()

    payload = session.catalog_course("COMPSCI", "189")

    assert payload["offerings_note"].endswith(reason)
    assert payload["offerings_note"].startswith("No scheduled sections are known")
    assert "offerings_note" not in payload["course"], "one note, not two"


def test_an_unknown_catalog_course_points_at_the_other_tools(session: Session, sample_catalog):
    with pytest.raises(ServiceError, match="check_offering"):
        session.catalog_course("STAT", "99999")


# -- budgets -------------------------------------------------------------------


def test_shrink_drops_whole_items_and_says_that_it_did():
    payload = {"items": [{"title": "x" * 100} for _ in range(50)], "counts": {"total": 50}}
    trimmed = shrink(payload, 1_000)
    assert len(json.dumps(trimmed)) <= 1_000
    assert trimmed["truncated"] is True
    assert any("omitted" in note for note in trimmed["warnings"])
    assert trimmed["counts"] == {"total": 50}, "summaries survive; only list items are dropped"


def test_shrink_leaves_a_small_payload_alone():
    payload = {"items": [1, 2, 3]}
    assert shrink(payload, 10_000) is payload


@pytest.mark.parametrize("name", list(BUDGETS))
def test_every_tool_has_a_declared_budget(name: str):
    assert BUDGETS[name] > 0


def test_real_payloads_stay_inside_their_budgets(session: Session, sample_catalog):
    session.index_course("1001")
    checks = {
        "list_courses": session.list_courses(),
        "get_deadlines": session.deadlines(window="month"),
        "get_assignment": session.assignment("1001", "201"),
        "get_course_overview": session.course_overview("1001"),
        "get_grades": session.grades("1001"),
        "find_materials": session.find_materials("1001", query="confounder"),
        "prepare_study_session": session.study_session("1001", "confounding"),
        "search_catalog": session.search_catalog(query="inference"),
        "get_catalog_course": session.catalog_course("COMPSCI", "189"),
    }
    for name, payload in checks.items():
        size = len(json.dumps(payload, default=str))
        assert size <= BUDGETS[name], f"{name} produced {size} bytes, budget {BUDGETS[name]}"


def test_every_payload_is_stamped(session: Session):
    for payload in (session.list_courses(), session.deadlines(), session.grades()):
        assert payload["as_of"].startswith("2026-09-04")
        assert payload["tz"] == "America/Los_Angeles"
        assert isinstance(payload["partial"], bool)
        assert isinstance(payload["warnings"], list)


# -- live offerings -------------------------------------------------------------


def test_check_offering_reads_the_class_schedule_and_caches_it(session: Session, monkeypatch):
    """Two requests on the first call, then none: the term list is stable for months."""
    from pathlib import Path

    import openmind.schedule as schedule_module

    fixtures = Path(__file__).parent / "fixtures" / "schedule"
    calls: list[str] = []

    def fake_fetch(url: str, *, client=None) -> str:
        calls.append(url)
        if "search=" in url:
            return (fixtures / "search_stat156_fall2026.html").read_text(encoding="utf-8")
        return (fixtures / "facets.html").read_text(encoding="utf-8")

    monkeypatch.setattr(schedule_module, "fetch", fake_fetch)

    payload = session.check_offering("stat 156")
    assert payload["term"] == "Fall 2026"
    assert payload["sections"][0]["instructors"] == "Peng Ding"
    assert payload["sections"][0]["ccn"] == "21143"
    assert payload["source"] == "classes.berkeley.edu"
    assert len(calls) == 2

    session.check_offering("stat 156")
    assert len(calls) == 2, "the whole answer is cached for a day"

    session.check_offering("compsci 189")
    assert len(calls) == 3, "a different course costs one request, not two"


def test_check_offering_says_when_a_term_is_not_posted_yet(session: Session, monkeypatch):
    from pathlib import Path

    import openmind.schedule as schedule_module

    fixtures = Path(__file__).parent / "fixtures" / "schedule"
    monkeypatch.setattr(
        schedule_module, "fetch",
        lambda url, client=None: (fixtures / "facets.html").read_text(encoding="utf-8"),
    )

    payload = session.check_offering("STAT 156", term="Spring 2028")
    assert payload["sections"] == []
    assert "not posted on the class schedule yet" in payload["note"]
    assert "Fall 2026" in payload["note"]


def test_a_string_that_is_not_a_course_code_is_refused(session: Session):
    with pytest.raises(ServiceError, match="does not look like a course code"):
        session.check_offering("something about machine learning")
