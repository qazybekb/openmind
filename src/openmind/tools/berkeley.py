"""Live Berkeley campus data — events and library hours."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Final, TypeAlias

import httpx

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

EVENTS_API_BASE: Final[str] = "https://events.berkeley.edu/live/json/events"
LIBRARY_HOURS_URL: Final[str] = "https://www.lib.berkeley.edu/hours"
REQUEST_TIMEOUT_S: Final[float] = 15.0

DEFAULT_EVENT_LIMIT: Final[int] = 15
MAX_EVENT_LIMIT: Final[int] = 30

# LibCal study room booking URLs for key libraries
STUDY_ROOM_URLS: Final[dict[str, str]] = {
    "Main Stacks": "https://berkeley.libcal.com/reserve/stacks",
    "Engineering": "https://berkeley.libcal.com/reserve/engi",
    "East Asian": "https://berkeley.libcal.com/reserve/eal",
    "Business": "https://berkeley.libcal.com/reserve/business",
    "Earth Sciences": "https://berkeley.libcal.com/reserve/EART",
    "Env Design": "https://berkeley.libcal.com/reserve/envi",
}

BERKELEY_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "berkeley_events",
            "description": "Search or list upcoming UC Berkeley campus events. Supports filtering by category (Academic, Lectures, Sports, Performing Arts, Films, Exhibits).",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Event category to filter by: Academic, Lectures, Sports, Performing Arts, Films, Exhibits, or omit for all",
                    },
                    "search": {
                        "type": "string",
                        "description": "Search query to filter events by title or description",
                    },
                    "featured": {
                        "type": "boolean",
                        "description": "Set to true to show only featured/starred events",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max events to return (default 15, max 30)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "berkeley_library_hours",
            "description": "Get current hours for UC Berkeley libraries. Scrapes the official lib.berkeley.edu/hours page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "library": {
                        "type": "string",
                        "description": "Specific library name to look up (e.g. 'Doe', 'Moffitt', 'Main Stacks', 'Business'). Omit for all.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "berkeley_study_rooms",
            "description": "Get study room booking links for UC Berkeley libraries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "library": {
                        "type": "string",
                        "description": "Library name (e.g. 'Main Stacks', 'Engineering', 'Business'). Omit for all.",
                    },
                },
                "required": [],
            },
        },
    },
]


def _json_result(payload: Any) -> str:
    """Serialize a Berkeley tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize a Berkeley tool error as JSON."""
    return _json_result({"error": message})


def _coerce_limit(value: Any) -> int:
    """Return a bounded event limit."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_EVENT_LIMIT
    return max(1, min(parsed, MAX_EVENT_LIMIT))


def execute_berkeley_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a Berkeley campus tool and return a JSON string."""
    del cfg  # Berkeley tools don't need user config

    try:
        return _execute_berkeley_tool(name, args)
    except httpx.HTTPError:
        logger.warning("Berkeley API request failed", exc_info=True)
        return _error_result("Failed to fetch Berkeley data.")
    except Exception:
        logger.exception("Berkeley tool '%s' failed unexpectedly", name)
        return _error_result("Berkeley tool failed unexpectedly.")


def _execute_berkeley_tool(name: str, args: ToolArgs) -> str:
    """Dispatch a Berkeley tool after validating arguments."""

    if name == "berkeley_events":
        return _fetch_events(args)

    if name == "berkeley_library_hours":
        return _fetch_library_hours(args)

    if name == "berkeley_study_rooms":
        return _fetch_study_rooms(args)

    return _error_result(f"Unknown berkeley tool: {name}")


def _fetch_events(args: ToolArgs) -> str:
    """Fetch upcoming events from the Berkeley events JSON API."""
    params: dict[str, str] = {}

    category = str(args.get("category", "")).strip()
    if category:
        params["category"] = category

    search = str(args.get("search", "")).strip()
    if search:
        params["search"] = search

    if args.get("featured"):
        params["starred"] = "true"

    limit = _coerce_limit(args.get("limit", DEFAULT_EVENT_LIMIT))

    resp = httpx.get(EVENTS_API_BASE, params=params, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    data = resp.json()

    if not isinstance(data, dict):
        return _error_result("Unexpected response from Berkeley events API.")

    raw_events = data.get("data", [])
    if not isinstance(raw_events, list):
        raw_events = []

    events: list[dict[str, str]] = []
    for event in raw_events[:limit]:
        if not isinstance(event, dict):
            continue

        event_data: dict[str, str] = {
            "title": str(event.get("title", "")),
            "date": str(event.get("date", "")),
            "time": str(event.get("date_time", "")),
            "url": str(event.get("url", "")),
        }

        # Location
        location = event.get("location", "")
        if location:
            event_data["location"] = str(location)

        # Online status
        if event.get("is_online"):
            online_type = str(event.get("online_type", "Online"))
            event_data["online"] = online_type
            online_url = event.get("online_url", "")
            if online_url:
                event_data["online_url"] = str(online_url)

        # Cost
        cost = event.get("cost", "")
        if cost:
            event_data["cost"] = str(cost)

        # Category
        categories = event.get("categories", [])
        if isinstance(categories, list) and categories:
            event_data["category"] = ", ".join(str(c) for c in categories[:3])

        # Cancellation
        if event.get("is_canceled"):
            event_data["canceled"] = "true"

        events.append(event_data)

    total = data.get("meta", {}).get("total_results", len(events)) if isinstance(data.get("meta"), dict) else len(events)

    return _json_result({
        "events": events,
        "count": len(events),
        "total_available": total,
        "source": "events.berkeley.edu",
    })


def _fetch_library_hours(args: ToolArgs) -> str:
    """Fetch library hours from lib.berkeley.edu/hours by scraping HTML.

    Since there's no JSON API for library hours, we fetch the HTML page
    and extract structured data. This is fragile but the best available option.
    """
    target_library = str(args.get("library", "")).strip().lower()

    resp = httpx.get(LIBRARY_HOURS_URL, timeout=REQUEST_TIMEOUT_S)
    resp.raise_for_status()
    html = resp.text

    # Parse the hours page — look for library names and hours patterns
    # The page uses a consistent structure with library names and hours
    libraries: list[dict[str, str]] = []

    # Simple HTML parsing — extract text between tags
    lines = html.replace("<br>", "\n").replace("<br/>", "\n").replace("</div>", "\n").replace("</li>", "\n")

    # Remove HTML tags but keep text
    import re
    clean_text = re.sub(r"<[^>]+>", " ", lines)
    clean_text = re.sub(r"\s+", " ", clean_text)

    # Known libraries to look for
    known_libraries = [
        "Doe Library", "Moffitt Library", "Main (Gardner) Stacks", "Bancroft Library",
        "Business Library", "East Asian Library", "Engineering Library",
        "Environmental Design Library", "Music Library", "Bioscience",
        "Earth Sciences", "Mathematics Statistics", "Social Research Library",
    ]

    for lib_name in known_libraries:
        if target_library and target_library not in lib_name.lower():
            continue

        # Find the library name and try to extract nearby hours text
        idx = clean_text.lower().find(lib_name.lower())
        if idx == -1:
            continue

        # Extract ~200 chars after the library name for hours info
        context = clean_text[idx:idx + 200].strip()

        # Look for hours patterns (e.g., "7 a.m.-10 p.m." or "Closed")
        hours_match = re.search(
            r"(\d{1,2}(?::\d{2})?\s*(?:a\.m\.|p\.m\.)\s*[-–]\s*\d{1,2}(?::\d{2})?\s*(?:a\.m\.|p\.m\.)|Closed|Open 24 hours|Limited|By appointment)",
            context,
            re.IGNORECASE,
        )

        libraries.append({
            "name": lib_name,
            "hours": hours_match.group(0) if hours_match else "Check website",
            "url": LIBRARY_HOURS_URL,
        })

    if not libraries:
        if target_library:
            return _json_result({
                "message": f"No hours found for '{target_library}'. Check {LIBRARY_HOURS_URL}",
                "url": LIBRARY_HOURS_URL,
            })
        return _json_result({
            "message": "Could not parse library hours. The page format may have changed.",
            "url": LIBRARY_HOURS_URL,
        })

    return _json_result({
        "libraries": libraries,
        "count": len(libraries),
        "note": "Hours may vary on holidays. Check lib.berkeley.edu/hours for the latest.",
        "source": LIBRARY_HOURS_URL,
    })


def _fetch_study_rooms(args: ToolArgs) -> str:
    """Return study room booking links for Berkeley libraries."""
    target = str(args.get("library", "")).strip().lower()

    rooms: list[dict[str, str]] = []
    for lib_name, url in STUDY_ROOM_URLS.items():
        if target and target not in lib_name.lower():
            continue
        rooms.append({"library": lib_name, "booking_url": url})

    if not rooms:
        if target:
            return _json_result({
                "message": f"No booking system found for '{target}'.",
                "all_libraries": list(STUDY_ROOM_URLS.keys()),
            })
        rooms = [{"library": k, "booking_url": v} for k, v in STUDY_ROOM_URLS.items()]

    return _json_result({
        "study_rooms": rooms,
        "count": len(rooms),
        "note": "Book via LibCal. Cal ID required.",
    })
