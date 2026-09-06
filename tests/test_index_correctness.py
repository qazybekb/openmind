"""The materials index must reflect what bCourses actually holds, and say when it does not.

Two failures here look identical to a student and are both quiet: a document that failed
once and is never retried, and a document that was deleted but keeps being quoted.
"""

from __future__ import annotations

import json

import httpx
import pytest

from openmind import index
from openmind.canvas import CanvasClient
from openmind.config import Config
from openmind.service import BUDGETS, Session
from tests.conftest import NOW_UTC, handler


def course_with(respond) -> CanvasClient:
    return CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond))


@pytest.fixture
def flaky_page(config: Config):
    """A course whose one page fails until the test says otherwise."""
    state = {"fail": True, "requests": 0}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses/1001/files":
            return httpx.Response(200, json=[], request=request)
        if request.url.path == "/api/v1/courses/1001/pages/week-3-notes":
            state["requests"] += 1
            if state["fail"]:
                return httpx.Response(503, json={}, request=request)
        return handler(request)

    client = course_with(respond)
    yield state, Session(config, client, clock=NOW_UTC)
    client.close()


# -- C1: retrying a transient failure ---------------------------------------------


def test_a_page_that_failed_once_is_requested_again_on_refresh(flaky_page):
    """A 503 is a bad minute at Canvas, not a permanent property of the document."""
    state, session = flaky_page

    first = session.index_course("1001")
    assert first["failed"] == 1
    assert state["requests"] == 1

    state["fail"] = False
    second = session.index_course("1001", refresh=True)

    assert state["requests"] == 2, "the failed page was never re-requested"
    assert second["failed"] == 0
    with index.connect() as conn:
        assert index.list_materials(conn, "1001", kind="page")[0]["status"] == "indexed"


def test_a_failure_that_persists_is_reported_every_time_not_just_the_first(flaky_page):
    """"failed: 0" while a document is still broken reads as "your index is complete"."""
    state, session = flaky_page
    session.index_course("1001")

    again = session.index_course("1001", refresh=True)

    assert again["failed"] == 1, "the outstanding total, not this pass's"
    assert again["partial"] is True
    assert any("could not be read" in note for note in again["warnings"])


def test_retrying_is_bounded_so_a_broken_document_is_not_requested_forever(flaky_page):
    state, session = flaky_page
    for _ in range(6):
        session.index_course("1001", refresh=True)

    assert state["requests"] <= index.MAX_ATTEMPTS


def test_a_routine_call_does_not_retry_failures(flaky_page):
    """Only an explicit refresh means "try again"; the ordinary path stays cheap."""
    state, session = flaky_page
    session.index_course("1001")
    session.index_course("1001")

    assert state["requests"] == 1


def test_pending_includes_failed_rows_only_when_asked(home):
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="page", canvas_id="p", title="Notes")
        index.mark(conn, material_id, "failed", "HTTP 503")

        assert index.pending(conn, "1") == []
        assert len(index.pending(conn, "1", retry_failed=True)) == 1


def test_a_successful_extraction_clears_the_attempt_count(home):
    from openmind.materials import Chunk

    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="page", canvas_id="p", title="Notes")
        index.mark(conn, material_id, "failed", "HTTP 503")
        index.store_chunks(conn, material_id, "Notes", [Chunk(ord=0, text="ok", page_start=1, page_end=1)])

        assert index.get_material(conn, material_id)["attempts"] == 0


# -- C2: reconciling removals ------------------------------------------------------


@pytest.fixture
def removable_page(config: Config):
    """A course whose page listing can be emptied mid-test."""
    state = {"deleted": False, "listing_fails": False}

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses/1001/files":
            return httpx.Response(200, json=[], request=request)
        if request.url.path == "/api/v1/courses/1001/pages":
            if state["listing_fails"]:
                return httpx.Response(503, json={}, request=request)
            if state["deleted"]:
                return httpx.Response(200, json=[], request=request)
        return handler(request)

    client = course_with(respond)
    yield state, Session(config, client, clock=NOW_UTC)
    client.close()


def test_a_page_removed_from_bcourses_stops_being_quoted(removable_page):
    """It used to keep returning its old excerpt with no warning at all."""
    state, session = removable_page
    session.index_course("1001")
    assert session.find_materials("1001", query="confounder", refresh=True)["hits"]

    state["deleted"] = True
    result = session.index_course("1001", refresh=True)

    assert any("removed from bCourses" in note for note in result["warnings"])
    assert session.find_materials("1001", query="confounder", refresh=True)["hits"] == []


def test_a_failed_listing_never_deletes_anything(removable_page):
    """Deleting a course's materials because Canvas had a bad minute is the worse error."""
    state, session = removable_page
    session.index_course("1001")

    state["listing_fails"] = True
    result = session.index_course("1001", refresh=True)

    assert any("pages could not be read" in note for note in result["warnings"])
    assert not any("removed from bCourses" in note for note in result["warnings"])
    assert session.find_materials("1001", query="confounder", refresh=True)["hits"]


def test_tombstoning_drops_the_chunks_too(home):
    from openmind.materials import Chunk

    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1", kind="page", canvas_id="gone", title="Old")
        index.store_chunks(conn, material_id, "Old", [Chunk(ord=0, text="stale text", page_start=1, page_end=1)])

        assert index.tombstone_missing(conn, "1", "page", {"still-here"}) == 1
        assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert index.search(conn, "1", "stale") == []


def test_a_material_still_present_is_left_alone(home):
    with index.connect() as conn:
        index.upsert_material(conn, course_id="1", kind="page", canvas_id="keep", title="Notes")
        assert index.tombstone_missing(conn, "1", "page", {"keep"}) == 0
        assert index.list_materials(conn, "1")[0]["status"] == "pending"


@pytest.mark.parametrize("kind", ["page", "file"])
def test_a_truncated_listing_preserves_unseen_materials(config, kind):
    from openmind.materials import Chunk

    endpoint = "pages" if kind == "page" else "files"
    params = {"published": "true", "per_page": "100"} if kind == "page" else {
        "sort": "updated_at", "order": "desc", "per_page": "100"
    }

    def respond(request):
        if request.url.path == f"/api/v1/courses/1001/{endpoint}":
            return httpx.Response(200, json=[], headers={
                "Link": f'<https://bcourses.berkeley.edu/api/v1/courses/1001/{endpoint}?page=2>; rel="next"'
            })
        return handler(request)

    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1001", kind=kind, canvas_id="unseen", title="Older Notes")
        index.store_chunks(conn, material_id, "Older Notes", [Chunk(ord=0, text="retain this evidence", page_start=1, page_end=1)])

    with course_with(respond) as client, index.connect() as conn:
        warnings = []
        Session(config, client)._discover_materials(conn, "1001", warnings, refresh=True)
        assert client.was_truncated(f"/courses/1001/{endpoint}", params)
        assert index.get_material(conn, material_id)["status"] == "indexed"
        assert index.search(conn, "1001", "retain")
        assert not any("removed from bCourses" in warning for warning in warnings)


def test_rediscovering_a_hidden_page_restores_its_text(removable_page):
    state, session = removable_page
    session.index_course("1001")
    state["deleted"] = True
    session.index_course("1001", refresh=True)
    state["deleted"] = False
    session.index_course("1001", refresh=True)
    assert session.find_materials("1001", query="confounder")["hits"]


def test_a_new_revision_resets_exhausted_retries(home):
    with index.connect() as conn:
        args = {"course_id": "1", "kind": "page", "canvas_id": "p", "title": "Notes"}
        material_id = index.upsert_material(conn, **args, source_updated_at="2026-09-01")
        for _ in range(index.MAX_ATTEMPTS):
            index.mark(conn, material_id, "failed", "HTTP 503")
        assert not index.pending(conn, "1", retry_failed=True)
        index.upsert_material(conn, **args, source_updated_at="2026-09-02")
        row = index.pending(conn, "1", retry_failed=True)[0]
        assert row["id"] == material_id
        assert row["attempts"] == 0 and row["status"] == "pending" and row["status_note"] is None


def test_search_results_carry_the_date_the_index_was_built(session: Session):
    session.index_course("1001")
    assert session.find_materials("1001", query="confounder")["indexed_at"].startswith("20")


# -- C3: budgets that reach nested and scalar fields --------------------------------


def oversized(field: str, size: int):
    """A Canvas that returns one very long prose field."""
    def respond(request: httpx.Request) -> httpx.Response:
        if field == "description" and request.url.path == "/api/v1/courses/1001/assignments/201":
            data = handler(request).json()
            data["description"] = "<p>" + "x" * size + "</p>"
            return httpx.Response(200, json=data, request=request)
        if field == "syllabus_body" and request.url.path == "/api/v1/courses/1001":
            data = handler(request).json()
            data["syllabus_body"] = "<p>" + "y" * size + "</p>"
            return httpx.Response(200, json=data, request=request)
        return handler(request)

    return respond


def encoded(payload: dict) -> int:
    return len(json.dumps(payload, default=str, separators=(",", ":")))


def test_an_assignment_description_cannot_push_the_payload_over_budget(config: Config):
    """`shrink` only drops list items, so a long string sailed straight past it."""
    with course_with(oversized("description", 9_000)) as client:
        payload = Session(config, client, clock=NOW_UTC).assignment("1001", "201", max_chars=8_000)

    assert encoded(payload) <= BUDGETS["get_assignment"]
    assert payload["description_chars"] == 9_000, "the full length is still reported"
    assert payload["description_cursor"] == len(payload["description"])


def test_walking_the_description_cursor_reassembles_the_whole_text(config: Config):
    with course_with(oversized("description", 9_000)) as client:
        session = Session(config, client, clock=NOW_UTC)
        collected, cursor = "", 0
        for _ in range(30):
            page = session.assignment("1001", "201", max_chars=8_000, cursor=cursor)
            collected += page["description"]
            if "description_cursor" not in page:
                break
            assert page["description_cursor"] > cursor
            cursor = page["description_cursor"]
        else:
            raise AssertionError("the walk never terminated")

    assert len(collected) == 9_000


def test_a_syllabus_cannot_push_the_overview_over_budget(config: Config):
    with course_with(oversized("syllabus_body", 20_000)) as client:
        payload = Session(config, client, clock=NOW_UTC).course_overview("1001", max_chars=8_000)

    assert encoded(payload) <= BUDGETS["get_course_overview"]
    assert payload["syllabus_chars"] == 20_000
    assert payload["syllabus_cursor"] == len(payload["syllabus"])


def test_a_short_description_is_returned_whole_with_no_cursor(config: Config):
    with course_with(handler) as client:
        payload = Session(config, client, clock=NOW_UTC).assignment("1001", "201")

    assert "average treatment effect" in payload["description"]
    assert "description_cursor" not in payload


@pytest.mark.parametrize("mode", ["tutor", "explain_assignment"])
def test_a_study_package_stays_in_budget_with_a_huge_assignment(config: Config, mode: str):
    """The description and rubric live inside `facts`, where `shrink` cannot reach them."""
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses/1001/assignments/201":
            data = handler(request).json()
            data["description"] = "<p>" + "x" * 20_000 + "</p>"
            data["rubric"] = [
                {"description": "Criterion " + "z" * 80, "points": 10,
                 "long_description": "<p>" + "w" * 900 + "</p>"}
                for _ in range(12)
            ]
            return httpx.Response(200, json=data, request=request)
        return handler(request)

    with course_with(respond) as client:
        payload = Session(config, client, clock=NOW_UTC).study_session(
            "1001", "Problem Set 3", mode=mode, assignment_id="201"
        )

    assert encoded(payload) <= BUDGETS["prepare_study_session"]
    assert payload["rules"], "the rules must survive the trimming, not the prose"
    assert payload["opening"]
