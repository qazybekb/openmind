"""Read from bCourses over a fixed set of routes.

Every method here is a GET against a route this module spells out itself. There is no
generic request helper reachable from a tool, so no course id, document, or model
output can steer a request somewhere else. The token is set once on the client and is
never returned, logged, or interpolated into a message.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any, Final
from urllib.parse import quote, urlparse

import httpx

from openmind.cache import DEFAULT_TTL_S, TTLCache, make_key
from openmind.config import ALLOWED_CANVAS_HOSTS

logger = logging.getLogger(__name__)

TIMEOUT_S: Final[float] = 30.0
DEFAULT_PAGE_SIZE: Final[str] = "100"
MAX_PAGES: Final[int] = 20
RETRY_AFTER_S: Final[float] = 2.0

JsonList = list[dict[str, Any]]
Params = Mapping[str, str | int | Sequence[str]]

_SAFE_ID = re.compile(r"^[0-9]+$")
_SAFE_SIS_ID = re.compile(r"^[A-Za-z0-9_:~-]+$")


class CanvasError(Exception):
    """A Canvas request failed in a way the student needs to hear about."""


def safe_id(value: object, what: str = "id") -> str:
    """Return a numeric Canvas id or raise :class:`CanvasError`."""
    text = str(value).strip()
    if not _SAFE_ID.match(text):
        raise CanvasError(f"{what} must be a numeric Canvas id, got {text[:40]!r}.")
    return text


def safe_slug(value: object, what: str = "page url") -> str:
    """Return a URL-encoded path segment for a Canvas page slug."""
    text = str(value).strip()
    if not text or len(text) > 200:
        raise CanvasError(f"{what} is missing or too long.")
    return quote(text, safe="")


def _flatten(params: Params | None) -> list[tuple[str, str]]:
    """Turn ``{"include[]": ["term", "total_scores"]}`` into repeated query keys.

    Canvas needs ``include[]=term&include[]=total_scores``. Passing a list to httpx
    does the right thing, but building the pairs explicitly keeps the behaviour
    obvious and testable.
    """
    pairs: list[tuple[str, str]] = []
    for key, value in (params or {}).items():
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(item)) for item in value)
        else:
            pairs.append((key, str(value)))
    return pairs


def _describe_error(status: int) -> str:
    """Map a Canvas HTTP status to something a student can act on."""
    if status == 401:
        return "Your bCourses token is invalid or expired. Run `openmind setup` to store a new one."
    if status == 403:
        return "bCourses denied access to that. Your token may not have permission for this resource."
    if status == 404:
        return "bCourses has no such item, or it is not visible to you."
    if status == 429:
        return "bCourses is rate limiting requests. Wait a minute and try again."
    if 500 <= status < 600:
        return f"bCourses returned a server error (HTTP {status}). Try again shortly."
    return f"The bCourses request failed with HTTP {status}."


class CanvasClient:
    """An authenticated, read-only bCourses client with a short-lived cache."""

    def __init__(self, base_url: str, token: str, *, cache: TTLCache | None = None, timeout: float = TIMEOUT_S,
                 transport: httpx.BaseTransport | None = None) -> None:
        host = (urlparse(base_url).hostname or "").lower().rstrip(".")
        if host not in ALLOWED_CANVAS_HOSTS:
            raise CanvasError(f"{base_url} is not a permitted Berkeley Canvas host.")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self.cache = cache if cache is not None else TTLCache()
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v1",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> CanvasClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- transport ---------------------------------------------------------

    def _request(self, path: str, params: Params | None = None, *, absolute: bool = False) -> httpx.Response:
        """Perform one GET, retrying once on a rate limit."""
        url = path if absolute else path
        for attempt in (0, 1):
            try:
                response = self._client.get(url, params=_flatten(params) or None)
            except httpx.HTTPError as exc:
                logger.warning("bCourses request to %s failed: %s", path, type(exc).__name__)
                raise CanvasError("Could not reach bCourses. Check your network connection.") from exc
            if response.status_code == 429 and attempt == 0:
                time.sleep(RETRY_AFTER_S)
                continue
            if response.status_code >= 400:
                logger.warning("bCourses returned HTTP %d for %s", response.status_code, path)
                raise CanvasError(_describe_error(response.status_code))
            return response
        raise CanvasError(_describe_error(429))  # pragma: no cover - loop always returns first

    def _get(self, path: str, params: Params | None = None, *, refresh: bool = False,
             ttl: float = DEFAULT_TTL_S) -> Any:
        """GET a single JSON document, through the cache."""
        key = make_key(path, dict(params or {}))
        cached = None if refresh else self.cache.get(key)
        if cached is not None:
            return cached
        data = self._request(path, params).json()
        self.cache.set(key, data, ttl)
        return data

    def _get_paginated(self, path: str, params: Params | None = None, *, refresh: bool = False,
                       ttl: float = DEFAULT_TTL_S, max_pages: int = MAX_PAGES) -> JsonList:
        """GET a list endpoint, following Canvas ``Link: rel="next"`` headers."""
        key = make_key("paged:" + path, dict(params or {}))
        cached = None if refresh else self.cache.get(key)
        if cached is not None:
            return cached

        merged = dict(params or {})
        merged.setdefault("per_page", DEFAULT_PAGE_SIZE)
        items: JsonList = []
        response = self._request(path, merged)
        for _ in range(max_pages):
            payload = response.json()
            if not isinstance(payload, list):
                raise CanvasError("bCourses returned an unexpected response for a list endpoint.")
            items.extend(entry for entry in payload if isinstance(entry, dict))
            next_url = _next_link(response.headers.get("link", ""))
            if not next_url:
                break
            response = self._request(next_url, None, absolute=True)

        self.cache.set(key, items, ttl)
        return items

    # -- fixed routes ------------------------------------------------------

    def profile(self, *, refresh: bool = False) -> dict[str, Any]:
        """Return the student's own Canvas profile, including their time zone."""
        data = self._get("/users/self/profile", refresh=refresh, ttl=3600.0)
        return data if isinstance(data, dict) else {}

    def courses(self, *, refresh: bool = False) -> JsonList:
        """Return active courses with term info and the student's own scores."""
        return self._get_paginated(
            "/courses",
            {"enrollment_state": "active", "include[]": ["term", "total_scores"], "per_page": "100"},
            refresh=refresh,
        )

    def planner_items(self, start_iso: str, end_iso: str, course_ids: Sequence[str] = (), *,
                      refresh: bool = False) -> JsonList:
        """Return planner items in a window, optionally restricted to some courses."""
        params: dict[str, str | Sequence[str]] = {"start_date": start_iso, "end_date": end_iso, "per_page": "100"}
        if course_ids:
            params["context_codes[]"] = [f"course_{safe_id(cid, 'course_id')}" for cid in course_ids]
        return self._get_paginated("/planner/items", params, refresh=refresh)

    def assignments(self, course_id: str, *, refresh: bool = False) -> JsonList:
        """Return every assignment in a course with the student's submission."""
        cid = safe_id(course_id, "course_id")
        return self._get_paginated(
            f"/courses/{cid}/assignments",
            {"include[]": ["submission"], "order_by": "due_at", "per_page": "100"},
            refresh=refresh,
        )

    def assignment(self, course_id: str, assignment_id: str, *, refresh: bool = False) -> dict[str, Any]:
        """Return one assignment with the student's submission and the rubric."""
        cid = safe_id(course_id, "course_id")
        aid = safe_id(assignment_id, "assignment_id")
        data = self._get(f"/courses/{cid}/assignments/{aid}", {"include[]": ["submission"]}, refresh=refresh)
        return data if isinstance(data, dict) else {}

    def assignment_groups(self, course_id: str, *, refresh: bool = False) -> JsonList:
        """Return assignment groups with weights, drop rules, and their assignments."""
        cid = safe_id(course_id, "course_id")
        return self._get_paginated(
            f"/courses/{cid}/assignment_groups",
            {"include[]": ["assignments"], "per_page": "100"},
            refresh=refresh,
        )

    def course(self, course_id: str, *, syllabus: bool = True, refresh: bool = False) -> dict[str, Any]:
        """Return one course, optionally including the syllabus body."""
        cid = safe_id(course_id, "course_id")
        params = {"include[]": ["syllabus_body", "term"]} if syllabus else {"include[]": ["term"]}
        data = self._get(f"/courses/{cid}", params, refresh=refresh)
        return data if isinstance(data, dict) else {}

    def modules(self, course_id: str, *, refresh: bool = False) -> JsonList:
        """Return course modules with their items."""
        cid = safe_id(course_id, "course_id")
        return self._get_paginated(
            f"/courses/{cid}/modules", {"include[]": ["items"], "per_page": "100"}, refresh=refresh
        )

    def announcements(self, course_ids: Sequence[str], start_iso: str, end_iso: str, *,
                      refresh: bool = False) -> JsonList:
        """Return announcements for some courses in a date window.

        Canvas defaults this endpoint to the last 14 days and needs ``context_codes[]``
        as repeated keys, so both are always sent explicitly.
        """
        if not course_ids:
            return []
        params: dict[str, str | Sequence[str]] = {
            "context_codes[]": [f"course_{safe_id(cid, 'course_id')}" for cid in course_ids],
            "start_date": start_iso,
            "end_date": end_iso,
            "per_page": "50",
        }
        return self._get_paginated("/announcements", params, refresh=refresh)

    def files(self, course_id: str, *, refresh: bool = False) -> JsonList:
        """Return course files newest first. Courses may hide this from students."""
        cid = safe_id(course_id, "course_id")
        return self._get_paginated(
            f"/courses/{cid}/files",
            {"sort": "updated_at", "order": "desc", "per_page": "100"},
            refresh=refresh,
        )

    def file(self, file_id: str, *, refresh: bool = False) -> dict[str, Any]:
        """Return a single file record, used when a module item omits the download URL."""
        fid = safe_id(file_id, "file_id")
        data = self._get(f"/files/{fid}", refresh=refresh)
        return data if isinstance(data, dict) else {}

    def pages(self, course_id: str, *, refresh: bool = False) -> JsonList:
        """Return published course pages."""
        cid = safe_id(course_id, "course_id")
        return self._get_paginated(
            f"/courses/{cid}/pages", {"published": "true", "per_page": "100"}, refresh=refresh
        )

    def page(self, course_id: str, page_url: str, *, refresh: bool = False) -> dict[str, Any]:
        """Return one course page including its HTML body."""
        cid = safe_id(course_id, "course_id")
        slug = safe_slug(page_url)
        data = self._get(f"/courses/{cid}/pages/{slug}", refresh=refresh)
        return data if isinstance(data, dict) else {}

    def enrollments(self, course_id: str, *, refresh: bool = False) -> JsonList:
        """Return the student's own enrollment in a course. Never another student's."""
        cid = safe_id(course_id, "course_id")
        return self._get_paginated(
            f"/courses/{cid}/enrollments", {"user_id": "self", "per_page": "50"}, refresh=refresh
        )

    def submissions(self, course_id: str, *, refresh: bool = False) -> JsonList:
        """Return the student's own graded submissions for a course."""
        cid = safe_id(course_id, "course_id")
        return self._get_paginated(
            f"/courses/{cid}/students/submissions",
            {"student_ids[]": ["self"], "per_page": "100", "order": "graded_at", "order_direction": "descending"},
            refresh=refresh,
        )


def _next_link(header: str) -> str | None:
    """Extract the ``rel="next"`` URL from a Canvas Link header."""
    for part in header.split(","):
        if 'rel="next"' in part:
            url = part.split(";")[0].strip().strip("<>")
            host = (urlparse(url).hostname or "").lower().rstrip(".")
            if host not in ALLOWED_CANVAS_HOSTS:
                logger.warning("Ignoring pagination link pointing off bCourses.")
                return None
            return url
    return None
