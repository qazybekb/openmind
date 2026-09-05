"""Every item a tool counts must be reachable by following its own cursor.

A cursor that advertises more than the page actually contained is worse than no
pagination: the host walks it, believes it has seen everything, and tells the student
their week is clear. These tests walk each paginated tool to exhaustion under a
deliberately small budget and assert that nothing is skipped or repeated.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from openmind import index, materials, service
from openmind.canvas import CanvasClient
from openmind.config import Config
from openmind.materials import Chunk
from openmind.service import Session, fit_page
from tests.conftest import NOW_UTC, canvas_dt, handler

MAX_PAGES = 80


@pytest.fixture
def tight_budget(monkeypatch: pytest.MonkeyPatch):
    """Shrink every budget so paging is exercised rather than skipped."""

    def apply(**budgets: int) -> None:
        for name, value in budgets.items():
            monkeypatch.setitem(service.BUDGETS, name, value)

    return apply


def walk(fetch, cursor_key: str, collect) -> tuple[list, int]:
    """Follow a tool's own cursor to exhaustion, returning what it yielded."""
    seen: list = []
    cursor = 0
    for page in range(MAX_PAGES):
        payload = fetch(cursor)
        seen.extend(collect(payload))
        if cursor_key not in payload:
            return seen, page + 1
        assert payload[cursor_key] > cursor, "a cursor that does not advance is an infinite loop"
        cursor = payload[cursor_key]
    raise AssertionError(f"still paging after {MAX_PAGES} pages")


# -- A1: deadlines ---------------------------------------------------------------


@pytest.fixture
def many_assignments(config: Config) -> CanvasClient:
    """A course with 30 assignments, more than one page at any budget."""
    assignments = [
        {"id": n, "name": f"Assignment {n:03}", "due_at": canvas_dt(1), "points_possible": 10,
         "submission_types": ["online_upload"], "submission": {"workflow_state": "unsubmitted"}}
        for n in range(1, 31)
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses/1001/assignments":
            return httpx.Response(200, json=assignments, request=request)
        return handler(request)

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond))
    yield client
    client.close()


@pytest.mark.parametrize("budget", [4_000, 1_500])
def test_walking_the_deadline_cursor_reaches_every_assignment(config, many_assignments, tight_budget, budget):
    """`next_offset` used to be the requested limit, so 19 of 30 were unreachable."""
    tight_budget(get_deadlines=budget)
    session = Session(config, many_assignments, clock=NOW_UTC)

    seen, pages = walk(
        lambda cursor: session.deadlines(status="all", course_id="1001", limit=25, offset=cursor),
        "next_offset",
        lambda payload: [int(i["assignment_id"]) for i in payload["overdue"] + payload["items"]],
    )

    assert pages > 1, "the fixture must actually paginate"
    assert sorted(seen) == list(range(1, 31))
    assert len(seen) == len(set(seen)), "no item may be handed out twice"


def test_a_deadline_page_never_promises_more_than_it_delivered(config, many_assignments, tight_budget):
    tight_budget(get_deadlines=1_500)
    session = Session(config, many_assignments, clock=NOW_UTC)
    page = session.deadlines(status="all", course_id="1001", limit=25)

    delivered = len(page["overdue"]) + len(page["items"])
    assert page["next_offset"] == delivered
    assert page["remaining"] == 30 - delivered


def test_overdue_work_is_reachable_through_the_same_cursor(config, tight_budget):
    """Overdue used to have no continuation at all, so a long list was truncated silently."""
    overdue_items = [
        {"id": n, "name": f"Late {n:03}", "due_at": canvas_dt(-4), "points_possible": 10,
         "submission_types": ["online_upload"],
         "submission": {"workflow_state": "unsubmitted", "missing": True}}
        for n in range(1, 21)
    ]

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses/1001/assignments":
            return httpx.Response(200, json=overdue_items, request=request)
        return handler(request)

    tight_budget(get_deadlines=1_200)
    with CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond)) as client:
        session = Session(config, client, clock=NOW_UTC)
        seen, pages = walk(
            lambda cursor: session.deadlines(status="all", course_id="1001", limit=25, offset=cursor),
            "next_offset",
            lambda payload: [int(i["assignment_id"]) for i in payload["overdue"]],
        )

    assert pages > 1
    assert sorted(seen) == list(range(1, 21))


def test_an_offset_past_the_end_is_an_empty_page_not_an_error(config, many_assignments):
    session = Session(config, many_assignments, clock=NOW_UTC)
    page = session.deadlines(status="all", course_id="1001", limit=25, offset=9_999)
    assert page["items"] == [] and page["overdue"] == []
    assert "next_offset" not in page


def test_fit_page_always_emits_one_record_even_when_it_cannot_fit(tight_budget):
    """A page of zero with a cursor pointing at itself is an infinite loop."""
    payload: dict = {"items": []}
    emitted = fit_page(payload, [("items", {"text": "x" * 5_000})], 100)
    assert emitted == 1
    assert len(payload["items"]) == 1


# -- A2: material listing --------------------------------------------------------


@pytest.fixture
def module_files(config: Config) -> CanvasClient:
    """A non-indexed course with seven files in one module."""
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses/1001/modules":
            return httpx.Response(200, request=request, json=[{"name": "Week 1", "items": [
                {"id": n, "content_id": n, "type": "File", "title": f"Reading {n}"} for n in range(1, 8)
            ]}])
        return handler(request)

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond))
    yield client
    client.close()


def test_walking_a_non_indexed_course_reaches_every_file(config, module_files):
    """Every cursor used to return page one, forever, while advertising the next."""
    session = Session(config, module_files, clock=NOW_UTC)
    seen, pages = walk(
        lambda cursor: session.find_materials("1001", limit=2, cursor=cursor),
        "next_cursor",
        lambda payload: [m["title"] for m in payload["materials"]],
    )

    assert pages == 4
    assert seen == [f"Reading {n}" for n in range(1, 8)]


def test_the_last_page_of_materials_offers_no_continuation(config, module_files):
    session = Session(config, module_files, clock=NOW_UTC)
    last = session.find_materials("1001", limit=2, cursor=6)
    assert [m["title"] for m in last["materials"]] == ["Reading 7"]
    assert "next_cursor" not in last


def test_a_full_page_with_nothing_after_it_does_not_advertise_more(config, module_files):
    """Seven files at limit 7 is exactly one page; a cursor here would return nothing."""
    session = Session(config, module_files, clock=NOW_UTC)
    page = session.find_materials("1001", limit=7)
    assert len(page["materials"]) == 7
    assert "next_cursor" not in page


def test_walking_an_indexed_course_reaches_every_material(session: Session, tight_budget):
    session.index_course("1001")
    tight_budget(find_materials=900)
    with index.connect() as conn:
        total = len(index.list_materials(conn, "1001", limit=100))

    seen, pages = walk(
        lambda cursor: session.find_materials("1001", limit=1, cursor=cursor),
        "next_cursor",
        lambda payload: [m["title"] for m in payload["materials"]],
    )
    assert pages == total, f"{total} materials should take {total} single-item pages"
    assert len(seen) == total
    assert len(seen) == len(set(seen))


def test_material_results_say_when_the_index_was_built(session: Session):
    session.index_course("1001")
    payload = session.find_materials("1001")
    assert payload["indexed_at"].startswith("20")


# -- A3: oversized material ------------------------------------------------------


def test_a_slide_longer_than_a_chunk_is_split_at_index_time(home: Path):
    chunks = materials.chunk_pages(["Study evidence " * 600], slides=True)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= materials.CHUNK_MAX for chunk in chunks)
    assert all(chunk.page_start == 1 for chunk in chunks), "the page marker survives the split"


def test_reading_an_oversized_chunk_makes_progress_instead_of_refusing(config, home: Path):
    """An index built before the chunk cap must still be readable, not a dead end."""
    body = "Study evidence " * 600
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1001", kind="file", canvas_id="501",
                                            title="Slides.pptx")
        index.store_chunks(conn, material_id, "Slides.pptx",
                           [Chunk(ord=0, text=body, page_start=1, page_end=1)], page_count=1)

    session = Session(config, clock=NOW_UTC)
    first = session.read_material(material_id)
    assert "Nothing left to read" not in first
    assert "Study evidence" in first
    assert len(first) <= service.BUDGETS["read_material"]


def test_walking_an_oversized_material_covers_every_character(config, home: Path):
    body = "Study evidence " * 600
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1001", kind="file", canvas_id="501",
                                            title="Slides.pptx")
        index.store_chunks(conn, material_id, "Slides.pptx",
                           [Chunk(ord=0, text=body, page_start=1, page_end=1)], page_count=1)
        rendered, _ = service._render_material(index.material_text(conn, material_id), paged=True)

    session = Session(config, clock=NOW_UTC)
    windows: list[tuple[int, int]] = []
    cursor = 0
    for _ in range(MAX_PAGES):
        text = session.read_material(material_id, cursor=cursor)
        assert len(text) <= service.BUDGETS["read_material"]
        if "read_material again with cursor=" not in text:
            windows.append((cursor, len(rendered)))
            break
        nxt = int(text.rsplit("cursor=", 1)[1].split()[0])
        assert nxt > cursor
        windows.append((cursor, nxt))
        cursor = nxt
    else:
        raise AssertionError("the walk never terminated")

    assert windows[0][0] == 0
    assert windows[-1][1] == len(rendered), "the last window reaches the end of the document"
    assert all(a[1] == b[0] for a, b in zip(windows, windows[1:], strict=False)), "windows are contiguous"


def test_a_continued_read_says_where_it_resumed(config, home: Path):
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1001", kind="file", canvas_id="501", title="Deck.pptx")
        index.store_chunks(conn, material_id, "Deck.pptx",
                           [Chunk(ord=0, text="Evidence " * 900, page_start=4, page_end=4)], page_count=9)

    text = Session(config, clock=NOW_UTC).read_material(material_id, cursor=3_000)
    assert "Continued from character 3000" in text
    assert "page 4" in text


def test_reading_past_the_end_says_so_rather_than_looping(config, home: Path):
    with index.connect() as conn:
        material_id = index.upsert_material(conn, course_id="1001", kind="page", canvas_id="p", title="Notes")
        index.store_chunks(conn, material_id, "Notes", [Chunk(ord=0, text="short", page_start=1, page_end=1)])

    assert "Nothing left to read" in Session(config, clock=NOW_UTC).read_material(material_id, cursor=10_000)


# -- payload budgets -------------------------------------------------------------


def test_every_deadline_page_respects_its_budget(config, many_assignments, tight_budget):
    tight_budget(get_deadlines=1_500)
    session = Session(config, many_assignments, clock=NOW_UTC)
    cursor = 0
    for _ in range(MAX_PAGES):
        page = session.deadlines(status="all", course_id="1001", limit=25, offset=cursor)
        emitted = len(page["overdue"]) + len(page["items"])
        size = len(json.dumps(page, default=str))
        assert size <= 1_500 or emitted == 1, f"{size} bytes for {emitted} items"
        if "next_offset" not in page:
            return
        cursor = page["next_offset"]
    raise AssertionError("the walk never terminated")
