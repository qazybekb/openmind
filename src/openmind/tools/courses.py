"""Search the UC Berkeley course catalog from bundled CSV data."""

from __future__ import annotations

import csv
import json
import logging
from importlib import resources
from typing import Any, Final, TypeAlias

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

DEFAULT_LIMIT: Final[int] = 15
MAX_LIMIT: Final[int] = 50

COURSE_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "berkeley_course_search",
            "description": "Search the UC Berkeley course catalog by subject, keyword, or department. Returns course titles, descriptions, units, and terms offered.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query — matches against subject, course number, title, or description (e.g. 'machine learning', 'CS 189', 'data science')",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Filter by subject code (e.g. 'COMPSCI', 'INFO', 'ECON', 'DATA')",
                    },
                    "level": {
                        "type": "string",
                        "description": "Filter by level: 'undergraduate' or 'graduate'",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results to return (default 15, max 50)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "berkeley_course_details",
            "description": "Get full details for a specific Berkeley course by subject and number (e.g. subject='COMPSCI', number='189').",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Subject code (e.g. 'COMPSCI', 'INFO', 'DATA')",
                    },
                    "number": {
                        "type": "string",
                        "description": "Course number (e.g. '189', '61A', '100')",
                    },
                },
                "required": ["subject", "number"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "berkeley_list_subjects",
            "description": "List all subject codes (departments) available in the Berkeley course catalog.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ---------------------------------------------------------------------------
# Catalog loading — cached in memory after first read
# ---------------------------------------------------------------------------

_catalog: list[dict[str, str]] | None = None

_CATALOG_FILES: Final[dict[str, str]] = {
    "undergraduate_courses.csv": "undergraduate",
    "graduate_courses.csv": "graduate",
}


def _load_catalog() -> list[dict[str, str]]:
    """Load undergraduate + graduate catalogs from package data. Cached after first call."""
    global _catalog
    if _catalog is not None:
        return _catalog

    _catalog = []
    for filename, level in _CATALOG_FILES.items():
        try:
            data_file = resources.files("openmind.data").joinpath(filename)
            text = data_file.read_text(encoding="utf-8")
            reader = csv.DictReader(text.splitlines())
            for row in reader:
                entry = dict(row)
                entry["_level"] = level
                _catalog.append(entry)
        except Exception:
            logger.warning("Failed to load %s catalog", level, exc_info=True)

    logger.info("Loaded %d courses from catalog", len(_catalog))
    return _catalog


def _format_course(row: dict[str, str]) -> dict[str, str]:
    """Format a catalog row into a clean course dict."""
    result: dict[str, str] = {
        "subject": row.get("Subject", ""),
        "number": row.get("Course Number", ""),
        "title": row.get("Course Title", ""),
        "units": row.get("Credits - Units - Minimum Units", ""),
        "department": row.get("Department(s)", ""),
        "level": row.get("_level", ""),
    }

    # Add max units if different from min
    max_units = row.get("Credits - Units - Maximum Units", "")
    if max_units and max_units != result["units"]:
        result["units"] = f"{result['units']}-{max_units}"

    desc = row.get("Course Description", "")
    if desc and desc != "-":
        # Truncate long descriptions
        if len(desc) > 300:
            desc = desc[:297] + "..."
        result["description"] = desc

    terms = row.get("Terms Offered", "")
    if terms and terms != "-":
        result["terms_offered"] = terms

    cross = row.get("Cross-Listed Course(s)", "")
    if cross and cross != "-":
        result["cross_listed"] = cross

    offering = row.get("Offering Information", "")
    if offering and offering != "-":
        result["offering_info"] = offering

    return result


def _coerce_limit(value: Any) -> int:
    """Return a bounded result limit."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(parsed, MAX_LIMIT))


def _json_result(payload: Any) -> str:
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    return _json_result({"error": message})


# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------


def execute_course_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a course catalog tool and return a JSON string."""
    del cfg

    try:
        return _execute_course_tool(name, args)
    except Exception:
        logger.exception("Course tool '%s' failed unexpectedly", name)
        return _error_result("Course catalog tool failed unexpectedly.")


def _execute_course_tool(name: str, args: ToolArgs) -> str:
    catalog = _load_catalog()
    if not catalog:
        return _error_result("Course catalog not available.")

    if name == "berkeley_course_search":
        query = str(args.get("query", "")).strip().lower()
        subject_filter = str(args.get("subject", "")).strip().upper()
        level_filter = str(args.get("level", "")).strip().lower()
        limit = _coerce_limit(args.get("limit", DEFAULT_LIMIT))

        matches: list[dict[str, str]] = []
        for row in catalog:
            subject = row.get("Subject", "")
            number = row.get("Course Number", "")
            title = row.get("Course Title", "")
            desc = row.get("Course Description", "")
            dept = row.get("Department(s)", "")
            level = row.get("_level", "")

            # Level filter
            if level_filter and level != level_filter:
                continue

            # Subject filter
            if subject_filter and subject.upper() != subject_filter:
                continue

            # Query filter — search across multiple fields
            if query:
                searchable = f"{subject} {number} {title} {desc} {dept}".lower()
                # All query words must match
                query_words = query.split()
                if not all(word in searchable for word in query_words):
                    continue

            matches.append(_format_course(row))
            if len(matches) >= limit:
                break

        return _json_result({
            "courses": matches,
            "count": len(matches),
            "total_in_catalog": len(catalog),
            "query": query or None,
            "subject_filter": subject_filter or None,
        })

    if name == "berkeley_course_details":
        subject = str(args.get("subject", "")).strip().upper()
        number = str(args.get("number", "")).strip()
        if not subject or not number:
            return _error_result("Both subject and number are required.")

        for row in catalog:
            if row.get("Subject", "").upper() == subject and row.get("Course Number", "").strip() == number:
                course = _format_course(row)
                # Include full description for detail view
                full_desc = row.get("Course Description", "")
                if full_desc and full_desc != "-":
                    course["description"] = full_desc
                # Include repeat rules
                repeat = row.get("Repeat Rules", "")
                if repeat and repeat != "-":
                    course["repeat_rules"] = repeat
                additional = row.get("Additional Offering Information", "")
                if additional and additional != "-":
                    course["additional_info"] = additional
                return _json_result({"course": course})

        return _error_result(f"Course not found: {subject} {number}")

    if name == "berkeley_list_subjects":
        subjects: dict[str, int] = {}
        for row in catalog:
            subj = row.get("Subject", "")
            if subj:
                subjects[subj] = subjects.get(subj, 0) + 1
        sorted_subjects = sorted(subjects.items(), key=lambda x: x[0])
        return _json_result({
            "subjects": [{"code": code, "course_count": count} for code, count in sorted_subjects],
            "total_subjects": len(sorted_subjects),
        })

    return _error_result(f"Unknown course tool: {name}")
