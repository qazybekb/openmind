"""The Canvas client's request shape, error handling, and pagination — plus the cache."""

from __future__ import annotations

import time

import httpx
import pytest

from openmind import cache as cache_module
from openmind.canvas import CanvasClient, CanvasError, _flatten, _next_link, safe_id, safe_slug
from tests.conftest import handler


def record(responder):
    """Wrap a responder so the test can inspect the requests that were made."""
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responder(request)

    return wrapped, seen


# -- request shape -------------------------------------------------------------


def test_repeated_query_keys_are_sent_the_way_canvas_needs_them():
    """`include[]=term&include[]=total_scores`, not a comma-joined list."""
    pairs = _flatten({"include[]": ["term", "total_scores"], "per_page": 100})
    assert pairs == [("include[]", "term"), ("include[]", "total_scores"), ("per_page", "100")]


def test_courses_asks_for_terms_and_scores_in_one_call():
    wrapped, seen = record(handler)
    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(wrapped))
    client.courses()
    client.close()
    params = seen[0].url.params
    assert params.get_list("include[]") == ["term", "total_scores"]
    assert params["enrollment_state"] == "active"


def test_announcements_send_context_codes_and_an_explicit_window():
    """Canvas silently defaults this endpoint to 14 days, so both dates are always sent."""
    wrapped, seen = record(handler)
    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(wrapped))
    client.announcements(["1001", "1002"], "2026-08-01T00:00:00Z", "2026-09-05T00:00:00Z")
    client.close()
    params = seen[0].url.params
    assert params.get_list("context_codes[]") == ["course_1001", "course_1002"]
    assert params["start_date"] == "2026-08-01T00:00:00Z"
    assert params["end_date"] == "2026-09-05T00:00:00Z"


def test_the_token_is_sent_as_a_bearer_header_and_not_in_the_url():
    wrapped, seen = record(handler)
    client = CanvasClient("https://bcourses.berkeley.edu", "secret-token", transport=httpx.MockTransport(wrapped))
    client.profile()
    client.close()
    assert seen[0].headers["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in str(seen[0].url)


def test_only_bcourses_may_be_addressed():
    with pytest.raises(CanvasError, match="not a permitted"):
        CanvasClient("https://canvas.instructure.com", "t")


# -- id validation -------------------------------------------------------------


@pytest.mark.parametrize("value", ["1001", 1001, " 1001 "])
def test_numeric_ids_are_accepted(value):
    assert safe_id(value) == "1001"


@pytest.mark.parametrize("value", ["../../users/1", "1001;DROP", "abc", "", "1 OR 1=1", "1001/enrollments"])
def test_anything_that_is_not_a_number_is_refused(value):
    with pytest.raises(CanvasError):
        safe_id(value, "course_id")


def test_page_slugs_are_url_encoded():
    assert safe_slug("../../secret") == "..%2F..%2Fsecret"
    assert safe_slug("week-3 notes") == "week-3%20notes"
    with pytest.raises(CanvasError):
        safe_slug("")


def test_a_bad_course_id_never_reaches_the_network():
    wrapped, seen = record(handler)
    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(wrapped))
    with pytest.raises(CanvasError):
        client.modules("../users/self")
    client.close()
    assert seen == []


# -- errors --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "fragment"),
    [
        (401, "invalid or expired"),
        (403, "denied access"),
        (404, "no such item"),
        (500, "server error"),
    ],
)
def test_http_errors_become_advice(status: int, fragment: str):
    client = CanvasClient(
        "https://bcourses.berkeley.edu", "t",
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={}, request=request)),
    )
    with pytest.raises(CanvasError, match=fragment):
        client.profile()
    client.close()


def test_a_rate_limit_is_retried_once_then_reported(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("openmind.canvas.time.sleep", lambda _: None)
    calls = {"n": 0}

    def limited(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(429, json={}, request=request)

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(limited))
    with pytest.raises(CanvasError, match="rate limiting"):
        client.profile()
    client.close()
    assert calls["n"] == 2


def test_a_network_failure_is_reported_as_a_network_failure():
    def dead(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(dead))
    with pytest.raises(CanvasError, match="Could not reach bCourses"):
        client.profile()
    client.close()


def test_a_token_never_appears_in_an_error_message():
    token = "1234~SuperSecret"
    client = CanvasClient(
        "https://bcourses.berkeley.edu", token,
        transport=httpx.MockTransport(lambda request: httpx.Response(401, json={}, request=request)),
    )
    with pytest.raises(CanvasError) as excinfo:
        client.profile()
    client.close()
    assert token not in str(excinfo.value)


# -- pagination ----------------------------------------------------------------


def test_link_headers_are_followed_across_pages():
    page_two = "https://bcourses.berkeley.edu/api/v1/courses?page=2"

    def paged(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[{"id": 2}], request=request)
        return httpx.Response(
            200, json=[{"id": 1}], request=request,
            headers={"link": f'<{page_two}>; rel="next", <{page_two}>; rel="last"'},
        )

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(paged))
    items = client._get_paginated("/courses")
    client.close()
    assert [item["id"] for item in items] == [1, 2]


def test_pagination_stops_at_the_page_limit():
    def endless(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=[{"id": 1}], request=request,
            headers={"link": '<https://bcourses.berkeley.edu/api/v1/courses?page=9>; rel="next"'},
        )

    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(endless))
    items = client._get_paginated("/courses", max_pages=3)
    client.close()
    assert len(items) == 3


def test_a_pagination_link_pointing_off_bcourses_is_ignored():
    assert _next_link('<https://evil.test/api/v1/courses?page=2>; rel="next"') is None
    assert _next_link('<https://bcourses.berkeley.edu/api/v1/x?page=2>; rel="next"') is not None
    assert _next_link("") is None


# -- cache ---------------------------------------------------------------------


def test_a_second_identical_call_does_not_hit_the_network():
    wrapped, seen = record(handler)
    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(wrapped))
    client.courses()
    client.courses()
    assert len(seen) == 1
    client.courses(refresh=True)
    assert len(seen) == 2
    client.close()


def test_different_parameters_are_cached_separately():
    wrapped, seen = record(handler)
    client = CanvasClient("https://bcourses.berkeley.edu", "t", transport=httpx.MockTransport(wrapped))
    client.planner_items("a", "b", ["1001"])
    client.planner_items("a", "b", ["1002"])
    client.close()
    assert len(seen) == 2


def test_entries_expire():
    cache = cache_module.TTLCache(ttl=0.01)
    cache.set("k", "v")
    assert cache.get("k") == "v"
    time.sleep(0.02)
    assert cache.get("k") is None


def test_get_or_set_computes_once():
    cache = cache_module.TTLCache()
    calls = {"n": 0}

    def factory() -> str:
        calls["n"] += 1
        return "value"

    assert cache.get_or_set("k", factory) == "value"
    assert cache.get_or_set("k", factory) == "value"
    assert calls["n"] == 1
    assert cache.get_or_set("k", factory, refresh=True) == "value"
    assert calls["n"] == 2


def test_the_cache_stays_bounded():
    cache = cache_module.TTLCache()
    for number in range(cache_module.MAX_ENTRIES + 50):
        cache.set(f"k{number}", number)
    assert len(cache) <= cache_module.MAX_ENTRIES


def test_keys_are_order_independent():
    assert cache_module.make_key("/x", {"a": 1, "b": 2}) == cache_module.make_key("/x", {"b": 2, "a": 1})
    assert cache_module.make_key("/x", {"a": ["p", "q"]}) == cache_module.make_key("/x", {"a": ["q", "p"]})
    assert cache_module.make_key("/x") != cache_module.make_key("/y")


def test_invalidating_by_prefix_leaves_other_entries():
    cache = cache_module.TTLCache()
    cache.set("courses:1", "a")
    cache.set("offering:x", "b")
    cache.invalidate("courses")
    assert cache.get("courses:1") is None
    assert cache.get("offering:x") == "b"
