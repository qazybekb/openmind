"""Limits that were declared but not enforced, and hops that carried the token too far.

Each of these is a case where the code said what it would do and then did something
else: a character cap that never applied, a page limit that cached a short list as
complete, a host check that let the scheme through.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import httpx
import pytest

from openmind import canvas as canvas_module
from openmind import index, materials
from openmind.canvas import CanvasClient, is_safe_hop
from openmind.config import Config
from openmind.service import Session
from tests.conftest import COURSES, NOW_UTC, handler

NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def pptx(slides: list[str]) -> bytes:
    """A .pptx whose compressed size says nothing about its expanded size."""
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for number, text in enumerate(slides, start=1):
            archive.writestr(
                f"ppt/slides/slide{number}.xml",
                f'<a:p xmlns:a="{NS}"><a:t>{text}</a:t></a:p>',
            )
    return body.getvalue()


# -- B1: extraction limits --------------------------------------------------------


def test_a_tiny_deck_that_expands_past_the_character_cap_is_truncated():
    """624 bytes on the wire became 400,100 characters in memory, flagged complete."""
    body = pptx(["x" * (materials.MAX_CHARS + 100)])

    result = materials.extract_pptx(body)

    assert len(body) < 2_000, "the archive itself is small; the expansion is the problem"
    assert result.char_count <= materials.MAX_CHARS
    assert result.truncated is True


def test_the_character_cap_is_cumulative_across_slides():
    """Ten slides each under the cap can still blow past it together."""
    result = materials.extract_pptx(pptx(["y" * 60_000] * 10))

    assert result.char_count <= materials.MAX_CHARS
    assert result.truncated is True


def test_a_deck_within_the_limits_is_not_flagged():
    result = materials.extract_pptx(pptx(["Confounding", "Randomisation"]))
    assert result.truncated is False
    assert result.char_count == len("Confounding") + len("Randomisation")


def test_a_zip_member_larger_than_the_cap_is_refused_rather_than_decompressed():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
        handle.writestr("big.xml", b"z" * 200_000)

    with zipfile.ZipFile(io.BytesIO(archive.getvalue())) as handle:
        with pytest.raises(materials._ExpansionLimit):
            materials.read_member(handle, "big.xml", 1_000)
        assert len(materials.read_member(handle, "big.xml", 500_000)) == 200_000


def test_an_oversized_word_document_is_skipped_with_a_reason():
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("word/document.xml", b"<w:document>" + b"z" * (materials.MAX_MEMBER_BYTES + 1) + b"</w:document>")

    result = materials.extract_docx(body.getvalue())
    assert result.status == "skipped"
    assert "too large" in (result.note or "")


def test_a_pdf_that_runs_past_its_deadline_stops_and_says_so(monkeypatch: pytest.MonkeyPatch):
    """The deadline was checked before each page, so one slow page could overrun it."""
    from tests.test_materials_and_index import make_pdf

    body = make_pdf([f"Page {n} of the reading" for n in range(1, 9)])
    ticks = iter([0.0] + [materials.MAX_SECONDS + 1] * 50)
    monkeypatch.setattr(materials.time, "monotonic", lambda: next(ticks))

    result = materials.extract_pdf(body)
    assert result.truncated is True
    assert result.page_count < 8


def test_the_course_index_stops_at_its_size_cap(session: Session, monkeypatch: pytest.MonkeyPatch):
    """MAX_COURSE_CHARS was declared and never applied to anything."""
    monkeypatch.setattr(index, "MAX_COURSE_CHARS", 200)

    result = session.index_course("1001")

    assert any("local index limit" in note for note in result["warnings"])
    assert result["partial"] is True
    with index.connect() as conn:
        assert index.course_chars(conn, "1001") < 20_000


def test_a_small_course_never_mentions_the_size_cap(session: Session):
    result = session.index_course("1001")
    assert not any("local index limit" in note for note in result["warnings"])


# -- B2: the page cap ------------------------------------------------------------


def paging_transport(calls: list[int]):
    """A Canvas that always claims one more page."""
    def respond(request: httpx.Request) -> httpx.Response:
        number = len(calls) + 1
        calls.append(number)
        return httpx.Response(200, json=[{"id": number}], request=request, headers={
            "Link": f'<https://bcourses.berkeley.edu/api/v1/courses?page={number + 1}>; rel="next"'
        })

    return httpx.MockTransport(respond)


def test_the_page_limit_stops_before_spending_a_request_it_would_discard():
    calls: list[int] = []
    with CanvasClient("https://bcourses.berkeley.edu", "t", transport=paging_transport(calls)) as client:
        items = client._get_paginated("/courses", max_pages=2)

    assert len(calls) == 2, "a third request was made and thrown away"
    assert len(items) == 2


def test_a_capped_list_is_marked_incomplete_rather_than_cached_as_whole():
    calls: list[int] = []
    with CanvasClient("https://bcourses.berkeley.edu", "t", transport=paging_transport(calls)) as client:
        client._get_paginated("/courses", max_pages=2)
        assert client.was_truncated("/courses") is True


def test_a_list_that_ends_naturally_is_not_marked_incomplete():
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1}], request=request)

    with CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond)) as client:
        client._get_paginated("/courses")
        assert client.was_truncated("/courses") is False


def test_a_truncated_read_makes_the_payload_partial(config: Config):
    """A short list presented as the whole set is the failure this guards against."""
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/courses":
            return httpx.Response(200, json=COURSES, request=request, headers={
                "Link": '<https://bcourses.berkeley.edu/api/v1/courses?page=2>; rel="next"'
            })
        return handler(request)

    with CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond)) as client:
        client._get_paginated("/courses", {"enrollment_state": "active"}, max_pages=1)
        payload = Session(config, client, clock=NOW_UTC).list_courses()

    assert payload["partial"] is True
    assert any("more pages" in note for note in payload["warnings"])


# -- B3: pagination hops ----------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "fragment"),
    [
        ("http://bcourses.berkeley.edu/api/v1/courses?page=2", "unencrypted"),
        ("https://evil.test/api/v1/courses?page=2", "not bCourses"),
        ("https://bcourses.berkeley.edu.evil.test/api/v1/courses", "not bCourses"),
        ("https://bcourses.berkeley.edu/login/oauth2/token", "outside /api/v1/"),
        ("https://bcourses.berkeley.edu/", "outside /api/v1/"),
        ("ftp://bcourses.berkeley.edu/api/v1/courses", "unencrypted"),
    ],
)
def test_an_unsafe_hop_is_named_and_refused(url: str, fragment: str):
    problem = is_safe_hop(url)
    assert problem is not None and fragment in problem


def test_a_legitimate_next_page_is_followed():
    assert is_safe_hop("https://bcourses.berkeley.edu/api/v1/courses?page=2") is None


def test_a_downgrade_link_never_puts_the_token_on_the_wire_in_the_clear():
    """The host check passed; only the scheme was wrong, and the Bearer rode along."""
    hops: list[dict] = []

    def respond(request: httpx.Request) -> httpx.Response:
        hops.append({"scheme": request.url.scheme, "token": "authorization" in request.headers})
        if len(hops) == 1:
            return httpx.Response(200, json=[], request=request, headers={
                "Link": '<http://bcourses.berkeley.edu/api/v1/courses?page=2>; rel="next"'
            })
        return httpx.Response(200, json=[], request=request)

    with CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond)) as client:
        client.courses()

    assert len(hops) == 1, "the downgrade hop must not be made at all"
    assert all(hop["scheme"] == "https" for hop in hops)


def test_an_off_api_link_is_not_followed():
    """A Link header naming the OAuth endpoint would send the token somewhere new."""
    urls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if len(urls) == 1:
            return httpx.Response(200, json=[], request=request, headers={
                "Link": '<https://bcourses.berkeley.edu/login/oauth2/token>; rel="next"'
            })
        return httpx.Response(200, json=[], request=request)

    with CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(respond)) as client:
        client.courses()

    assert len(urls) == 1
    assert "oauth2" not in urls[0]


def test_the_page_limit_constant_is_still_what_callers_get(home: Path):
    assert canvas_module.MAX_PAGES == 20


# -- C2/C3: logging and measurement -------------------------------------------------


def test_the_server_quiets_the_http_client_loggers(monkeypatch: pytest.MonkeyPatch):
    """httpx logs every request at INFO, turning the daily 404 check into stderr noise."""
    import logging

    from openmind import server

    for name in ("httpx", "httpcore", "openmind"):
        logging.getLogger(name).setLevel(logging.NOTSET)
    monkeypatch.setattr(server.mcp, "run", lambda *a, **k: None)

    server.main()

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
    assert logging.getLogger("openmind").level == logging.INFO


def test_budgets_are_measured_the_way_the_tools_serialise():
    """Measuring with Python's default spacing stopped every page hundreds of bytes early."""
    from openmind import server
    from openmind.service import encoded_size

    payload = {"courses": [{"subject": "STAT", "number": "156", "title": "Causal Inference"}] * 5}
    assert encoded_size(payload) == len(server._json(payload))
    assert encoded_size(payload) < len(json.dumps(payload, default=str))
