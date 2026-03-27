"""Reminder scheduling — set and check local reminders."""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final, TypeAlias

from openmind.config import CONFIG_DIR, ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

REMINDERS_FILE: Final[Path] = CONFIG_DIR / "reminders.json"

REMINDER_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "remind_me",
            "description": (
                "Set a reminder for the student. Use this when they say things like "
                "'remind me', 'don't let me forget', 'I need to remember'. "
                "Provide an ISO datetime and a message."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "What to remind about"},
                    "due_at": {
                        "type": "string",
                        "description": "ISO 8601 datetime (e.g. '2026-03-28T09:00:00')",
                    },
                },
                "required": ["message", "due_at"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": "List all pending reminders.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _load_reminders() -> list[dict[str, Any]]:
    """Load reminders from disk."""
    if not REMINDERS_FILE.exists():
        return []
    try:
        data = json.loads(REMINDERS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _save_reminders(reminders: list[dict[str, Any]]) -> None:
    """Persist reminders atomically."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(reminders, handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_file = Path(tmp_path)
        tmp_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp_file.replace(REMINDERS_FILE)
    except OSError:
        logger.warning("Failed to save reminders", exc_info=True)
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def get_due_reminders() -> list[dict[str, Any]]:
    """Return and remove reminders that are past due."""
    reminders = _load_reminders()
    now = datetime.now(timezone.utc)

    due: list[dict[str, Any]] = []
    remaining: list[dict[str, Any]] = []

    for reminder in reminders:
        try:
            due_at = datetime.fromisoformat(str(reminder.get("due_at", "")))
            if due_at.tzinfo is None:
                due_at = due_at.replace(tzinfo=timezone.utc)
            if due_at <= now:
                due.append(reminder)
            else:
                remaining.append(reminder)
        except (ValueError, TypeError):
            remaining.append(reminder)

    if due:
        _save_reminders(remaining)

    return due


def execute_reminder_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a reminder tool."""
    if name == "remind_me":
        message = str(args.get("message", "")).strip()
        due_at = str(args.get("due_at", "")).strip()

        if not message:
            return json.dumps({"error": "Missing required argument: message."})
        if not due_at:
            return json.dumps({"error": "Missing required argument: due_at."})

        try:
            datetime.fromisoformat(due_at)
        except ValueError:
            return json.dumps({"error": f"Invalid datetime format: {due_at}. Use ISO 8601."})

        reminders = _load_reminders()
        reminders.append({
            "message": message,
            "due_at": due_at,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_reminders(reminders)

        return json.dumps({"result": f"Reminder set: '{message}' at {due_at}"})

    if name == "list_reminders":
        reminders = _load_reminders()
        if not reminders:
            return json.dumps({"reminders": [], "message": "No reminders set."})

        items = []
        for r in reminders:
            items.append({"message": r.get("message", ""), "due_at": r.get("due_at", "")})
        return json.dumps({"reminders": items})

    return json.dumps({"error": f"Unknown reminder tool: {name}"})
