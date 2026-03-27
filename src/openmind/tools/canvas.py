"""Call the Canvas API through LLM-facing tools."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any, Final, TypeAlias

import httpx

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]
JsonPayload: TypeAlias = dict[str, Any] | list[Any]

CANVAS_TIMEOUT_S: Final[float] = 30.0
DEFAULT_PAGE_SIZE: Final[str] = "100"
MAX_PAGINATION_PAGES: Final[int] = 20

CANVAS_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_assignments",
            "description": "Get all upcoming assignments and events across all courses, sorted by due date.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_assignments",
            "description": "Get assignments for a specific course, including submission status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_grades",
            "description": "Get current grades/enrollment for a specific course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_all_grades",
            "description": "Get current grades for ALL active courses at once.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_assignment_details",
            "description": "Get full details of a specific assignment including description, rubric, and due date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                    "assignment_id": {"type": "string", "description": "Canvas assignment ID"},
                },
                "required": ["course_id", "assignment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_assignment_groups",
            "description": "Get assignment group weights for a course (for grade calculations).",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_modules",
            "description": "Get course modules with items (weeks, topics, readings).",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_page_content",
            "description": "Get the HTML content of a specific Canvas page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                    "page_url": {"type": "string", "description": "Canvas page URL slug"},
                },
                "required": ["course_id", "page_url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_course_files",
            "description": "List files in a course (lectures, slides, readings). Returns download URLs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                    "search_term": {"type": "string", "description": "Optional search filter for file name"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_announcements",
            "description": "Get recent announcements for one or all courses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Specific course ID, or omit for all courses"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_syllabus",
            "description": "Get the syllabus for a course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_discussion_topics",
            "description": "Get discussion topics for a course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "course_id": {"type": "string", "description": "Canvas course ID"},
                },
                "required": ["course_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_course_id",
            "description": "Look up a Canvas course ID from a course nickname (e.g. 'NLP', 'Finance').",
            "parameters": {
                "type": "object",
                "properties": {
                    "nickname": {"type": "string", "description": "Course nickname or partial name"},
                },
                "required": ["nickname"],
            },
        },
    },
]

_cached_client: httpx.Client | None = None
_cached_client_key: str = ""


def _json_result(payload: Any) -> str:
    """Serialize a tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str, **extra: Any) -> str:
    """Serialize a tool error as JSON."""
    payload: dict[str, Any] = {"error": message}
    payload.update(extra)
    return _json_result(payload)


def _normalise_courses(cfg: Mapping[str, Any]) -> dict[str, str]:
    """Return configured course IDs and names as strings."""
    raw_courses = cfg.get("courses", {})
    if not isinstance(raw_courses, dict):
        return {}

    return {str(course_id): str(course_name) for course_id, course_name in raw_courses.items()}


_SAFE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def _required_str(args: ToolArgs, key: str) -> str | None:
    """Return a required string argument or `None` when it is missing."""
    value = str(args.get(key, "")).strip()
    return value or None


def _safe_id(args: ToolArgs, key: str) -> str | None:
    """Return a validated ID argument safe for use in URL paths, or None."""
    value = str(args.get(key, "")).strip()
    if not value:
        return None
    if not _SAFE_ID_PATTERN.match(value):
        logger.warning("Rejected unsafe %s value: %s", key, value[:50])
        return None
    return value


def _get_client(cfg: Mapping[str, Any]) -> httpx.Client | None:
    """Return a reusable Canvas client when config is complete."""
    global _cached_client, _cached_client_key

    from openmind.config import validate_canvas_url

    canvas_url = str(cfg.get("canvas_url", "")).rstrip("/")
    canvas_token = str(cfg.get("canvas_token", ""))
    if not canvas_url or not canvas_token:
        return None
    if not validate_canvas_url(canvas_url):
        logger.warning("Canvas URL %s is not in the allowed hosts list", canvas_url)
        return None

    client_key = f"{canvas_url}:{canvas_token}"
    if _cached_client is None or _cached_client_key != client_key:
        if _cached_client is not None:
            _cached_client.close()

        _cached_client = httpx.Client(
            base_url=canvas_url,
            headers={"Authorization": f"Bearer {canvas_token}"},
            timeout=CANVAS_TIMEOUT_S,
        )
        _cached_client_key = client_key

    return _cached_client


def _handle_http_error(error: httpx.HTTPStatusError) -> dict[str, str]:
    """Map Canvas HTTP errors to actionable messages."""
    status_code = error.response.status_code
    if status_code == 401:
        return {"error": "Canvas token is invalid or expired. Run: openmind setup"}
    if status_code == 403:
        return {"error": "Access denied. Your Canvas token may not have permission for this resource."}
    if status_code == 429:
        return {"error": "Canvas rate limit hit. Wait a minute and try again."}
    return {"error": f"Canvas request failed with HTTP {status_code}."}


def _get(
    cfg: Mapping[str, Any],
    path: str,
    params: Mapping[str, str] | None = None,
) -> JsonPayload:
    """Execute a single GET request against Canvas."""
    client = _get_client(cfg)
    if client is None:
        return {"error": "Canvas is not configured. Run: openmind setup"}

    try:
        response = client.get(path, params=dict(params or {}))
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        logger.warning("Canvas request failed with HTTP %d for %s", error.response.status_code, path)
        return _handle_http_error(error)
    except httpx.HTTPError:
        logger.warning("Canvas request failed for %s", path, exc_info=True)
        return {"error": "Canvas request failed. Check your network connection and Canvas URL."}

    data = response.json()
    if isinstance(data, (dict, list)):
        return data
    return {"error": "Canvas returned an unexpected response type."}


def _get_paginated(
    cfg: Mapping[str, Any],
    path: str,
    params: Mapping[str, str] | None = None,
    *,
    max_pages: int = MAX_PAGINATION_PAGES,
) -> JsonPayload:
    """Execute a paginated GET request against Canvas."""
    client = _get_client(cfg)
    if client is None:
        return {"error": "Canvas is not configured. Run: openmind setup"}

    items: list[Any] = []
    request_path = path
    request_params: dict[str, str] | None = dict(params or {})
    if request_params is not None and "per_page" not in request_params:
        request_params["per_page"] = DEFAULT_PAGE_SIZE

    for _ in range(max_pages):
        try:
            response = client.get(request_path, params=request_params if request_path == path else None)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            logger.warning("Canvas pagination failed with HTTP %d for %s", error.response.status_code, path)
            return _handle_http_error(error)
        except httpx.HTTPError:
            logger.warning("Canvas pagination failed for %s", path, exc_info=True)
            return {"error": "Canvas request failed. Check your network connection and Canvas URL."}

        data = response.json()
        if isinstance(data, list):
            items.extend(data)
        elif isinstance(data, dict):
            return data
        else:
            return {"error": "Canvas returned an unexpected response type."}

        next_url: str | None = None
        for part in response.headers.get("link", "").split(","):
            if 'rel="next"' in part:
                next_url = part.split(";")[0].strip().strip("<>")
                break

        if not next_url:
            break

        request_path = next_url
        request_params = None

    return items


def execute_canvas_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a Canvas tool and return a JSON string."""
    try:
        return _execute_canvas_tool(name, args, cfg)
    except Exception:
        logger.exception("Canvas tool '%s' failed unexpectedly", name)
        return _error_result("Canvas tool failed unexpectedly.")


def _execute_canvas_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Dispatch a Canvas tool after validating its arguments."""
    courses = _normalise_courses(cfg)

    if name == "lookup_course_id":
        nickname = str(args.get("nickname", "")).strip().lower()
        if not nickname:
            return _error_result("Missing required argument: nickname.")

        for course_id, course_name in courses.items():
            if nickname == course_name.lower():
                return _json_result({"course_id": course_id, "name": course_name})

        candidates = [
            (course_id, course_name)
            for course_id, course_name in courses.items()
            if nickname in course_name.lower()
        ]
        if len(candidates) == 1:
            return _json_result({"course_id": candidates[0][0], "name": candidates[0][1]})
        if len(candidates) > 1:
            return _error_result(
                f"Ambiguous: '{nickname}' matches multiple courses. Be more specific.",
                candidates={course_id: course_name for course_id, course_name in candidates},
            )
        return _error_result(f"No course matching '{nickname}'", available=courses)

    if name == "get_upcoming_assignments":
        data = _get(cfg, "/users/self/upcoming_events")
        if isinstance(data, list):
            data = [event for event in data if isinstance(event, dict) and event.get("assignment")]
        return _json_result(data)

    if name == "get_course_assignments":
        course_id = _safe_id(args, "course_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        data = _get_paginated(
            cfg,
            f"/courses/{course_id}/assignments",
            {"include[]": "submission", "order_by": "due_at"},
        )
        # Flag upcoming deadlines so the LLM doesn't ignore them
        if isinstance(data, list):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            upcoming = []
            for a in data:
                if not isinstance(a, dict):
                    continue
                due = a.get("due_at", "")
                if not due or due < now:
                    continue
                sub = a.get("submission", {})
                ws = sub.get("workflow_state", "") if isinstance(sub, dict) else ""
                if ws not in ("submitted", "graded"):
                    upcoming.append({
                        "name": a.get("name", ""),
                        "due_at": due,
                        "points_possible": a.get("points_possible"),
                        "submission_state": ws or "unsubmitted",
                    })
            if upcoming:
                return _json_result({
                    "WARNING": f"This course has {len(upcoming)} UPCOMING DEADLINES that are NOT YET SUBMITTED. You MUST tell the student about these.",
                    "UPCOMING_DEADLINES": upcoming,
                    "all_assignments": data,
                })
            return _json_result({"all_assignments": data, "UPCOMING_DEADLINES": []})
        return _json_result(data)

    if name == "get_grades":
        course_id = _safe_id(args, "course_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        data = _get(cfg, f"/courses/{course_id}/enrollments", {"user_id": "self"})
        return _json_result(data)

    if name == "get_all_grades":
        results: dict[str, dict[str, Any]] = {}
        for course_id, course_name in courses.items():
            data = _get(cfg, f"/courses/{course_id}/enrollments", {"user_id": "self"})
            if not isinstance(data, list):
                continue

            for enrollment in data:
                if not isinstance(enrollment, dict):
                    continue

                grades = enrollment.get("grades", {})
                if not isinstance(grades, dict):
                    continue

                if grades.get("current_score") is not None:
                    results[course_name] = {
                        "score": grades.get("current_score"),
                        "grade": grades.get("current_grade"),
                    }
        return _json_result(results)

    if name == "get_assignment_details":
        course_id = _safe_id(args, "course_id")
        assignment_id = _safe_id(args, "assignment_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        if assignment_id is None:
            return _error_result("Missing required argument: assignment_id.")
        data = _get(cfg, f"/courses/{course_id}/assignments/{assignment_id}")
        return _json_result(data)

    if name == "get_assignment_groups":
        course_id = _safe_id(args, "course_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        data = _get(cfg, f"/courses/{course_id}/assignment_groups")
        return _json_result(data)

    if name == "get_modules":
        course_id = _safe_id(args, "course_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        data = _get_paginated(cfg, f"/courses/{course_id}/modules", {"include[]": "items"})
        return _json_result(data)

    if name == "get_page_content":
        course_id = _safe_id(args, "course_id")
        page_url = _required_str(args, "page_url")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        if page_url is None:
            return _error_result("Missing required argument: page_url.")
        # URL-encode page_url to prevent path traversal
        from urllib.parse import quote
        safe_page_url = quote(page_url, safe="")
        data = _get(cfg, f"/courses/{course_id}/pages/{safe_page_url}")
        return _json_result(data)

    if name == "get_course_files":
        course_id = _safe_id(args, "course_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")

        params: dict[str, str] = {}
        search_term = str(args.get("search_term", "")).strip()
        if search_term:
            params["search_term"] = search_term

        data = _get_paginated(cfg, f"/courses/{course_id}/files", params or None)
        return _json_result(data)

    if name == "get_announcements":
        course_id = str(args.get("course_id", "")).strip()
        context_codes = [f"course_{course_id}"] if course_id else [f"course_{cid}" for cid in courses]
        params: dict[str, str] = {"per_page": "50"}
        for index, context_code in enumerate(context_codes):
            params[f"context_codes[{index}]"] = context_code
        data = _get_paginated(cfg, "/announcements", params)
        return _json_result(data)

    if name == "get_syllabus":
        course_id = _safe_id(args, "course_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        data = _get(cfg, f"/courses/{course_id}", {"include[]": "syllabus_body"})
        return _json_result(data)

    if name == "get_discussion_topics":
        course_id = _safe_id(args, "course_id")
        if course_id is None:
            return _error_result("Missing required argument: course_id.")
        data = _get_paginated(cfg, f"/courses/{course_id}/discussion_topics")
        return _json_result(data)

    return _error_result(f"Unknown canvas tool: {name}")
