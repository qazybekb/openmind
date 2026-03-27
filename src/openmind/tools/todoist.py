"""Manage Todoist tasks through simple LLM tools."""

from __future__ import annotations

import json
import logging
from typing import Any, Final, TypeAlias

import httpx

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

API_BASE: Final[str] = "https://api.todoist.com/api/v1"
MAX_LISTED_TASKS: Final[int] = 30
REQUEST_TIMEOUT_S: Final[float] = 15.0

TODOIST_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "todoist_add_task",
            "description": "Add a task to Todoist with an optional due date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Task title (e.g. 'NLP — Midterm report')"},
                    "due_string": {"type": "string", "description": "Due date (e.g. '2026-03-21' or 'Friday')"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "todoist_list_tasks",
            "description": "List active tasks from Todoist.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _json_result(payload: Any) -> str:
    """Serialize a Todoist tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize a Todoist tool error as JSON."""
    return _json_result({"error": message})


def _get_token(cfg: ConfigDict) -> str | None:
    """Return the Todoist API token when Todoist is enabled."""
    todoist = cfg.get("todoist", {})
    if not todoist.get("enabled"):
        return None

    token = str(todoist.get("token", "")).strip()
    return token or None


def execute_todoist_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a Todoist tool and return a JSON string."""
    token = _get_token(cfg)
    if token is None:
        return _error_result("Todoist is not connected yet. The student can set it up by running: openmind setup todoist. They will need their Todoist API token from Settings > Integrations > Developer.")

    headers = {"Authorization": f"Bearer {token}"}

    try:
        return _execute_todoist_tool(name, args, headers)
    except Exception:
        logger.exception("Todoist tool '%s' failed unexpectedly", name)
        return _error_result("Todoist tool failed unexpectedly.")


def _execute_todoist_tool(name: str, args: ToolArgs, headers: dict[str, str]) -> str:
    """Dispatch a Todoist tool after validating its arguments."""
    if name == "todoist_add_task":
        content = str(args.get("content", "")).strip()
        if not content:
            return _error_result("Missing required argument: content.")

        body: dict[str, str] = {"content": content}
        due_string = str(args.get("due_string", "")).strip()
        if due_string:
            body["due_string"] = due_string

        try:
            response = httpx.post(f"{API_BASE}/tasks", json=body, headers=headers, timeout=REQUEST_TIMEOUT_S)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Todoist add task failed", exc_info=True)
            return _error_result("Failed to add the Todoist task.")

        task = response.json()
        if not isinstance(task, dict):
            return _error_result("Todoist returned an unexpected response.")
        return _json_result({"result": f"Added: {task.get('content', '')}", "id": task.get("id")})

    if name == "todoist_list_tasks":
        try:
            response = httpx.get(f"{API_BASE}/tasks", headers=headers, timeout=REQUEST_TIMEOUT_S)
            response.raise_for_status()
        except httpx.HTTPError:
            logger.warning("Todoist list tasks failed", exc_info=True)
            return _error_result("Failed to list Todoist tasks.")

        data = response.json()
        # v1 API wraps results: {"results": [...], "next_cursor": ...}
        if isinstance(data, dict):
            tasks = data.get("results", [])
        elif isinstance(data, list):
            tasks = data
        else:
            return _error_result("Todoist returned an unexpected response.")

        items: list[dict[str, Any]] = []
        for task in tasks[:MAX_LISTED_TASKS]:
            if not isinstance(task, dict):
                continue

            due = task.get("due", {})
            due_date = due.get("date") if isinstance(due, dict) else None
            items.append({"content": task.get("content", ""), "due": due_date})
        return _json_result({"tasks": items, "count": len(items)})

    return _error_result(f"Unknown todoist tool: {name}")
