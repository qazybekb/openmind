"""Search and read Slack messages through read-only tools."""

from __future__ import annotations

import json
import logging
from typing import Any, Final, TypeAlias

import httpx

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

API_BASE: Final[str] = "https://slack.com/api"
DEFAULT_MESSAGE_LIMIT: Final[int] = 20
MAX_MESSAGE_LIMIT: Final[int] = 50
MAX_SEARCH_RESULTS: Final[int] = 20
REQUEST_TIMEOUT_S: Final[float] = 15.0

SLACK_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "slack_search",
            "description": "Search Slack messages across all accessible channels. Returns matching messages with sender, channel, and timestamp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (e.g. 'midterm', 'from:@professor', 'in:#nlp')"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "slack_read_channel",
            "description": "Read recent messages from a specific Slack channel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel": {"type": "string", "description": "Channel name (e.g. 'nlp-announcements') or channel ID"},
                    "limit": {"type": "integer", "description": "Number of messages to fetch (default 20, max 50)"},
                },
                "required": ["channel"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "slack_list_channels",
            "description": "List Slack channels the user has access to.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


def _json_result(payload: Any) -> str:
    """Serialize a Slack tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize a Slack tool error as JSON."""
    return _json_result({"error": message})


def _get_token(cfg: ConfigDict) -> str | None:
    """Return the Slack user token when Slack is enabled."""
    slack = cfg.get("slack", {})
    if not slack.get("enabled"):
        return None
    token = str(slack.get("token", "")).strip()
    return token or None


def _slack_api(token: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a Slack Web API method and return the parsed response."""
    resp = httpx.get(
        f"{API_BASE}/{method}",
        params=params or {},
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT_S,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        return {"ok": False, "error": "unexpected_response"}
    return data


def _resolve_channel_id(token: str, channel_name: str) -> str | None:
    """Resolve a channel name to its ID. Returns None if not found."""
    channel_name = channel_name.lstrip("#").strip()
    if not channel_name:
        return None

    # If it looks like a channel ID already (starts with C/G), use it directly
    if len(channel_name) > 8 and channel_name[0] in ("C", "G"):
        return channel_name

    try:
        data = _slack_api(token, "conversations.list", {
            "types": "public_channel,private_channel",
            "limit": "200",
            "exclude_archived": "true",
        })
        if not data.get("ok"):
            return None
        for ch in data.get("channels", []):
            if not isinstance(ch, dict):
                continue
            if ch.get("name", "").lower() == channel_name.lower():
                return str(ch.get("id", ""))
    except Exception:
        logger.warning("Failed to resolve Slack channel '%s'", channel_name, exc_info=True)
    return None


def _coerce_limit(value: Any) -> int:
    """Return a bounded message limit."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_MESSAGE_LIMIT
    return max(1, min(parsed, MAX_MESSAGE_LIMIT))


def execute_slack_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute a Slack tool and return a JSON string."""
    token = _get_token(cfg)
    if not token:
        return _error_result("Slack not configured. Run: openmind setup")

    try:
        return _execute_slack_tool(name, args, token)
    except httpx.HTTPError:
        logger.warning("Slack API request failed", exc_info=True)
        return _error_result("Slack API request failed.")
    except Exception:
        logger.exception("Slack tool '%s' failed unexpectedly", name)
        return _error_result("Slack tool failed unexpectedly.")


def _execute_slack_tool(name: str, args: ToolArgs, token: str) -> str:
    """Dispatch a Slack tool after validating its arguments."""
    if name == "slack_search":
        query = str(args.get("query", "")).strip()
        if not query:
            return _error_result("Missing required argument: query.")

        data = _slack_api(token, "search.messages", {
            "query": query,
            "count": str(MAX_SEARCH_RESULTS),
            "sort": "timestamp",
            "sort_dir": "desc",
        })
        if not data.get("ok"):
            return _error_result(f"Slack search failed: {data.get('error', 'unknown')}")

        messages_data = data.get("messages", {})
        matches = messages_data.get("matches", []) if isinstance(messages_data, dict) else []

        results: list[dict[str, str]] = []
        for match in matches:
            if not isinstance(match, dict):
                continue
            results.append({
                "text": str(match.get("text", "")),
                "user": str(match.get("username", "")),
                "channel": str(match.get("channel", {}).get("name", "")) if isinstance(match.get("channel"), dict) else "",
                "timestamp": str(match.get("ts", "")),
                "permalink": str(match.get("permalink", "")),
            })

        return _json_result({"messages": results, "count": len(results)})

    if name == "slack_read_channel":
        channel_input = str(args.get("channel", "")).strip()
        if not channel_input:
            return _error_result("Missing required argument: channel.")

        channel_id = _resolve_channel_id(token, channel_input)
        if not channel_id:
            return _error_result(f"Channel not found: {channel_input}")

        limit = _coerce_limit(args.get("limit", DEFAULT_MESSAGE_LIMIT))
        data = _slack_api(token, "conversations.history", {
            "channel": channel_id,
            "limit": str(limit),
        })
        if not data.get("ok"):
            error = data.get("error", "unknown")
            if error == "not_in_channel":
                return _error_result(f"You're not a member of #{channel_input}.")
            return _error_result(f"Failed to read channel: {error}")

        messages: list[dict[str, str]] = []
        for msg in data.get("messages", []):
            if not isinstance(msg, dict):
                continue
            messages.append({
                "text": str(msg.get("text", "")),
                "user": str(msg.get("user", "")),
                "timestamp": str(msg.get("ts", "")),
                "type": str(msg.get("subtype", "message")),
            })

        return _json_result({"channel": channel_input, "messages": messages, "count": len(messages)})

    if name == "slack_list_channels":
        data = _slack_api(token, "conversations.list", {
            "types": "public_channel,private_channel",
            "limit": "200",
            "exclude_archived": "true",
        })
        if not data.get("ok"):
            return _error_result(f"Failed to list channels: {data.get('error', 'unknown')}")

        channels: list[dict[str, Any]] = []
        for ch in data.get("channels", []):
            if not isinstance(ch, dict):
                continue
            channels.append({
                "name": str(ch.get("name", "")),
                "id": str(ch.get("id", "")),
                "topic": str(ch.get("topic", {}).get("value", "")) if isinstance(ch.get("topic"), dict) else "",
                "member_count": ch.get("num_members", 0),
            })

        return _json_result({"channels": channels, "count": len(channels)})

    return _error_result(f"Unknown slack tool: {name}")
