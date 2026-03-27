"""Collect and dispatch the LLM tool definitions used by OpenMind."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, TypeAlias

from openmind.config import ConfigDict
from openmind.tools.berkeley import BERKELEY_TOOLS, execute_berkeley_tool
from openmind.tools.calendar import CALENDAR_TOOLS, execute_calendar_tool
from openmind.tools.canvas import CANVAS_TOOLS, execute_canvas_tool
from openmind.tools.courses import COURSE_TOOLS, execute_course_tool
from openmind.tools.gmail import GMAIL_TOOLS, execute_gmail_tool
from openmind.tools.obsidian import OBSIDIAN_TOOLS, execute_obsidian_tool
from openmind.tools.pdf import PDF_TOOLS, execute_pdf_tool
from openmind.tools.profile import PROFILE_TOOLS, execute_profile_tool
from openmind.tools.reminders import REMINDER_TOOLS, execute_reminder_tool
from openmind.tools.slack import SLACK_TOOLS, execute_slack_tool
from openmind.tools.todoist import TODOIST_TOOLS, execute_todoist_tool
from openmind.tools.web import WEB_TOOLS, execute_web_tool

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]
ToolExecutor: TypeAlias = Callable[[str, ToolArgs, ConfigDict], str]

_TOOL_GROUPS: dict[str, tuple[list[ToolDefinition], ToolExecutor]] = {
    "canvas": (CANVAS_TOOLS, execute_canvas_tool),
    "berkeley": (BERKELEY_TOOLS, execute_berkeley_tool),
    "courses": (COURSE_TOOLS, execute_course_tool),
    "pdf": (PDF_TOOLS, execute_pdf_tool),
    "profile": (PROFILE_TOOLS, execute_profile_tool),
    "reminders": (REMINDER_TOOLS, execute_reminder_tool),
    "web": (WEB_TOOLS, execute_web_tool),
    "obsidian": (OBSIDIAN_TOOLS, execute_obsidian_tool),
    "todoist": (TODOIST_TOOLS, execute_todoist_tool),
    "gmail": (GMAIL_TOOLS, execute_gmail_tool),
    "slack": (SLACK_TOOLS, execute_slack_tool),
    "calendar": (CALENDAR_TOOLS, execute_calendar_tool),
}


def get_all_tools(cfg: ConfigDict) -> list[ToolDefinition]:
    """Return tool definitions for the integrations enabled in config."""
    tools: list[ToolDefinition] = [*CANVAS_TOOLS, *BERKELEY_TOOLS, *COURSE_TOOLS, *PROFILE_TOOLS, *REMINDER_TOOLS, *PDF_TOOLS, *WEB_TOOLS]

    if cfg.get("obsidian", {}).get("enabled"):
        tools.extend(OBSIDIAN_TOOLS)
    if cfg.get("todoist", {}).get("enabled"):
        tools.extend(TODOIST_TOOLS)
    if cfg.get("gmail", {}).get("enabled"):
        tools.extend(GMAIL_TOOLS)
    if cfg.get("slack", {}).get("enabled"):
        tools.extend(SLACK_TOOLS)
    if cfg.get("calendar", {}).get("enabled"):
        tools.extend(CALENDAR_TOOLS)

    return tools


def execute_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a tool by name and return a JSON string."""
    for group_tools, executor in _TOOL_GROUPS.values():
        if name not in {tool["function"]["name"] for tool in group_tools}:
            continue

        try:
            return executor(name, args, cfg)
        except Exception:
            logger.exception("Tool '%s' failed unexpectedly", name)
            return json.dumps({"error": "Tool execution failed unexpectedly."})

    return json.dumps({"error": f"Unknown tool: {name}"})
