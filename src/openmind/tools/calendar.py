"""Manage Google Calendar events through optional tools."""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Final, TypeAlias

from openmind.config import ConfigDict, GMAIL_CREDS_DIR

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

# Reuses the Gmail credentials directory — same Google OAuth app
CALENDAR_TOKEN_FILE = GMAIL_CREDS_DIR / "calendar_token.json"
SCOPES: Final[list[str]] = ["https://www.googleapis.com/auth/calendar.events"]

DEFAULT_DAYS_AHEAD: Final[int] = 7
MAX_DAYS_AHEAD: Final[int] = 30
DEFAULT_DURATION_MINUTES: Final[int] = 60
MAX_EVENTS: Final[int] = 30

CALENDAR_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "calendar_list_events",
            "description": "List upcoming events from Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "How many days ahead to look (default 7, max 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_add_event",
            "description": "Create a new event on Google Calendar. Use for deadlines, study blocks, or reminders.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title (e.g. 'NLP Midterm Report Due')"},
                    "date": {"type": "string", "description": "Date in YYYY-MM-DD format (e.g. '2026-04-01')"},
                    "time": {"type": "string", "description": "Start time in HH:MM format, 24h (e.g. '14:00'). Omit for all-day events."},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes (default 60). Ignored for all-day events."},
                },
                "required": ["title", "date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_add_deadlines",
            "description": "Bulk-add Canvas assignment deadlines to Google Calendar. Takes a list of assignments with titles and due dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "assignments": {
                        "type": "array",
                        "description": "List of assignments to add",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "Assignment title (e.g. 'NLP — Midterm Report')"},
                                "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD format"},
                            },
                            "required": ["title", "due_date"],
                        },
                    },
                },
                "required": ["assignments"],
            },
        },
    },
]


def _ensure_private_google_dir() -> None:
    """Create the shared Google credentials directory with owner-only permissions."""
    GMAIL_CREDS_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(GMAIL_CREDS_DIR, stat.S_IRWXU)


def _restrict_file(path: Any) -> None:
    """Restrict a credential or token file to owner read/write."""
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def _json_result(payload: Any) -> str:
    """Serialize a Calendar tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize a Calendar tool error as JSON."""
    return _json_result({"error": message})


def _coerce_days(value: Any) -> int:
    """Return a bounded days-ahead value."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_DAYS_AHEAD
    return max(1, min(parsed, MAX_DAYS_AHEAD))


def _get_calendar_service(cfg: ConfigDict) -> Any | None:
    """Build a Google Calendar API service using stored OAuth credentials.

    Shares the same OAuth credentials directory as Gmail. If both are enabled,
    the student only needs to authenticate once via Google Cloud Console.
    """
    if not cfg.get("calendar", {}).get("enabled"):
        return None

    creds_file = GMAIL_CREDS_DIR / "credentials.json"
    if not creds_file.exists():
        return None

    try:
        # Lazy import — Google API deps are optional
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None

    try:
        credentials: Any | None = None
        if CALENDAR_TOKEN_FILE.exists():
            credentials = Credentials.from_authorized_user_file(str(CALENDAR_TOKEN_FILE), SCOPES)

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            elif CALENDAR_TOKEN_FILE.exists():
                return None  # Token exists but can't refresh
            else:
                if not sys.stdin.isatty():
                    return None  # Can't do interactive auth in headless mode
                flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
                credentials = flow.run_local_server(port=0)
            _ensure_private_google_dir()
            CALENDAR_TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")
            _restrict_file(CALENDAR_TOKEN_FILE)

        return build("calendar", "v3", credentials=credentials)
    except Exception:
        logger.warning("Failed to initialize Google Calendar service", exc_info=True)
        return None


_NOT_READY_MSG: Final[str] = (
    "Google Calendar not ready. Either: (1) run pip install 'openmind[calendar]', "
    "(2) run openmind chat for browser auth, or "
    "(3) delete ~/.openmind/gmail/calendar_token.json and re-auth."
)


def execute_calendar_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a Calendar tool and return a JSON string."""
    service = _get_calendar_service(cfg)
    if service is None:
        return _error_result(_NOT_READY_MSG)

    try:
        return _execute_calendar_tool(name, args, service)
    except Exception:
        logger.exception("Calendar tool '%s' failed unexpectedly", name)
        return _error_result("Calendar tool failed unexpectedly.")


def _execute_calendar_tool(name: str, args: ToolArgs, service: Any) -> str:
    """Dispatch a Calendar tool after validating its arguments."""
    if name == "calendar_list_events":
        days = _coerce_days(args.get("days_ahead", DEFAULT_DAYS_AHEAD))
        now = datetime.now(timezone.utc)
        time_max = now + timedelta(days=days)

        results = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat(),
            timeMax=time_max.isoformat(),
            maxResults=MAX_EVENTS,
            singleEvents=True,
            orderBy="startTime",
        ).execute()

        events: list[dict[str, str]] = []
        for event in results.get("items", []):
            if not isinstance(event, dict):
                continue
            start = event.get("start", {})
            start_str = start.get("dateTime", start.get("date", "")) if isinstance(start, dict) else ""
            events.append({
                "title": str(event.get("summary", "")),
                "start": start_str,
                "location": str(event.get("location", "")),
                "id": str(event.get("id", "")),
            })

        return _json_result({"events": events, "count": len(events), "days_ahead": days})

    if name == "calendar_add_event":
        title = str(args.get("title", "")).strip()
        date = str(args.get("date", "")).strip()
        if not title:
            return _error_result("Missing required argument: title.")
        if not date:
            return _error_result("Missing required argument: date.")

        # Validate date format
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return _error_result(f"Invalid date format: '{date}'. Use YYYY-MM-DD.")

        time_str = str(args.get("time", "")).strip()

        if time_str:
            # Validate time format
            try:
                datetime.strptime(time_str, "%H:%M")
            except ValueError:
                return _error_result(f"Invalid time format: '{time_str}'. Use HH:MM (24h).")

            # Validate duration
            try:
                raw_duration = int(args.get("duration_minutes", DEFAULT_DURATION_MINUTES))
            except (TypeError, ValueError):
                raw_duration = DEFAULT_DURATION_MINUTES
            duration = max(15, min(raw_duration, 480))

            start_dt = datetime.fromisoformat(f"{date}T{time_str}:00")
            end_dt = start_dt + timedelta(minutes=duration)
            event_body = {
                "summary": title,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "America/Los_Angeles"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "America/Los_Angeles"},
            }
        else:
            # All-day event
            event_body = {
                "summary": title,
                "start": {"date": date},
                "end": {"date": date},
            }

        created = service.events().insert(calendarId="primary", body=event_body).execute()
        return _json_result({
            "result": f"Added: {title}",
            "date": date,
            "id": created.get("id", ""),
            "link": created.get("htmlLink", ""),
        })

    if name == "calendar_add_deadlines":
        assignments = args.get("assignments", [])
        if not isinstance(assignments, list) or not assignments:
            return _error_result("Missing required argument: assignments (list).")

        added: list[str] = []
        failed: list[str] = []

        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue
            a_title = str(assignment.get("title", "")).strip()
            a_date = str(assignment.get("due_date", "")).strip()
            if not a_title or not a_date:
                continue

            try:
                event_body = {
                    "summary": f"\U0001f4da {a_title}",
                    "start": {"date": a_date},
                    "end": {"date": a_date},
                    "reminders": {
                        "useDefault": False,
                        "overrides": [
                            {"method": "popup", "minutes": 24 * 60},  # 1 day before
                            {"method": "popup", "minutes": 60},       # 1 hour before
                        ],
                    },
                }
                service.events().insert(calendarId="primary", body=event_body).execute()
                added.append(f"{a_title} ({a_date})")
            except Exception:
                logger.warning("Failed to add deadline '%s'", a_title, exc_info=True)
                failed.append(a_title)

        result: dict[str, Any] = {"added": added, "added_count": len(added)}
        if failed:
            result["failed"] = failed
        return _json_result(result)

    return _error_result(f"Unknown calendar tool: {name}")
