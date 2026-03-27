"""Call the configured LLM through OpenRouter and execute tools."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Final, TypeAlias

from openai import APIError, APITimeoutError, OpenAI

from openmind.config import ConfigDict
from openmind.personality import build_system_prompt
from openmind.tools import execute_tool, get_all_tools

logger = logging.getLogger(__name__)

ChatMessage: TypeAlias = dict[str, Any]

DEFAULT_MODEL: Final[str] = "google/gemini-2.5-pro"
MAX_TOOL_OUTPUT_CHARS: Final[int] = 16_000
MAX_TOOL_ROUNDS: Final[int] = 10
MAX_HISTORY: Final[int] = 40
OPENROUTER_API_BASE: Final[str] = "https://openrouter.ai/api/v1"
OPENROUTER_TIMEOUT_S: Final[float] = 60.0
RETRY_DELAYS: Final[tuple[int, ...]] = (1, 2, 4)
SENSITIVE_TOOL_LOOKBACK_USER_MESSAGES: Final[int] = 2
SENSITIVE_TOOL_KEYWORDS: Final[dict[str, tuple[str, ...]]] = {
    "gmail_search": ("email", "emails", "gmail", "inbox", "mail", "reply", "replied"),
    "gmail_read": ("email", "emails", "gmail", "inbox", "mail", "reply", "replied"),
    "slack_search": ("slack", "channel", "channels"),
    "slack_read_channel": ("slack", "channel", "channels"),
    "slack_list_channels": ("slack", "channel", "channels"),
    "calendar_list_events": ("calendar", "event", "events", "schedule", "scheduled", "meeting"),
    "calendar_add_event": ("calendar", "event", "events", "schedule", "scheduled", "meeting", "block", "reminder", "remind"),
    "calendar_add_deadlines": ("calendar", "event", "events", "schedule", "scheduled", "deadline", "deadlines", "reminder"),
    "todoist_add_task": ("todoist", "task", "tasks", "todo", "to-do"),
    "todoist_list_tasks": ("todoist", "task", "tasks", "todo", "to-do"),
    "obsidian_read": ("obsidian", "note", "notes", "vault", "markdown"),
    "obsidian_write": ("obsidian", "note", "notes", "vault", "markdown", "save"),
    "obsidian_search": ("obsidian", "note", "notes", "vault", "search my notes"),
}
SENSITIVE_TOOL_ERROR: Final[str] = (
    "This integration is only available when the student explicitly asks about email, Slack, calendar, tasks, or notes."
)


def _is_transient(exc: Exception) -> bool:
    """Return True if the error is transient and worth retrying."""
    if isinstance(exc, APITimeoutError):
        return True
    if isinstance(exc, APIError):
        return exc.status_code in (429, 500, 502, 503, 504) if exc.status_code else False
    return False


def _truncate_tool_output(text: str) -> str:
    """Truncate long tool output to prevent context bloat."""
    if len(text) <= MAX_TOOL_OUTPUT_CHARS:
        return text
    return text[:MAX_TOOL_OUTPUT_CHARS] + "\n... (truncated)"


def _cast_tool_args(args: dict[str, Any], tools: list[dict[str, Any]], fn_name: str) -> dict[str, Any]:
    """Cast tool arguments to match the schema types (e.g. '5' -> 5 for integers)."""
    for tool in tools:
        func = tool.get("function", {})
        if func.get("name") != fn_name:
            continue
        props = func.get("parameters", {}).get("properties", {})
        for key, schema in props.items():
            if key not in args:
                continue
            expected = schema.get("type")
            val = args[key]
            if expected == "integer" and isinstance(val, str):
                try:
                    args[key] = int(val)
                except ValueError:
                    pass
            elif expected == "number" and isinstance(val, str):
                try:
                    args[key] = float(val)
                except ValueError:
                    pass
            elif expected == "boolean" and isinstance(val, str):
                args[key] = val.lower() in ("true", "1", "yes")
        break
    return args


def create_client(cfg: ConfigDict) -> OpenAI:
    """Create an OpenAI-compatible client pointed at OpenRouter."""
    return OpenAI(
        base_url=OPENROUTER_API_BASE,
        api_key=str(cfg.get("openrouter_api_key", "")),
        timeout=OPENROUTER_TIMEOUT_S,
    )


def _recent_user_messages(conversation: list[ChatMessage]) -> list[str]:
    """Return the most recent user messages, newest first."""
    recent: list[str] = []
    for message in reversed(conversation):
        if message.get("role") != "user":
            continue
        recent.append(str(message.get("content", "")).lower())
        if len(recent) >= SENSITIVE_TOOL_LOOKBACK_USER_MESSAGES:
            break
    return recent


def _user_explicitly_requested_tool(name: str, conversation: list[ChatMessage]) -> bool:
    """Return whether recent user messages explicitly mention a sensitive integration."""
    keywords = SENSITIVE_TOOL_KEYWORDS.get(name)
    if not keywords:
        return True

    recent_messages = _recent_user_messages(conversation)
    return any(any(keyword in message for keyword in keywords) for message in recent_messages)


def chat(
    cfg: ConfigDict,
    messages: list[ChatMessage],
    *,
    client: OpenAI | None = None,
) -> str:
    """Send messages to the LLM, execute tool calls, and return the final reply."""
    if client is None:
        client = create_client(cfg)

    model = str(cfg.get("model", DEFAULT_MODEL))
    tools = get_all_tools(cfg)
    conversation: list[ChatMessage] = list(messages)

    # Ensure system prompt is the first message
    if not conversation or conversation[0].get("role") != "system":
        system_prompt = build_system_prompt(cfg)
        conversation = [{"role": "system", "content": system_prompt}, *conversation]

    # Trim history to stay within context limits
    if len(conversation) > MAX_HISTORY + 1:
        conversation = [conversation[0], *conversation[-MAX_HISTORY:]]

    for _ in range(MAX_TOOL_ROUNDS):
        # LLM call with retry on transient errors
        response = None
        for attempt, delay in enumerate((*RETRY_DELAYS, 0)):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=conversation,
                    tools=tools if tools else None,
                )
                break
            except Exception as exc:
                if _is_transient(exc) and attempt < len(RETRY_DELAYS):
                    logger.warning("Transient LLM error (attempt %d), retrying in %ds: %s", attempt + 1, delay, exc)
                    time.sleep(delay)
                else:
                    raise

        if response is None:
            return "Sorry, I couldn't reach the AI model. Please try again."

        choice = response.choices[0]
        message = choice.message

        if not message.tool_calls:
            return message.content or ""

        # Append assistant message with tool calls
        conversation.append(message.model_dump(exclude_none=True))

        # Execute each tool call and append results
        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
                if not isinstance(fn_args, dict):
                    fn_args = {}
            except (json.JSONDecodeError, TypeError):
                fn_args = {}

            # Type-cast args to match schema
            fn_args = _cast_tool_args(fn_args, tools, fn_name)

            if not _user_explicitly_requested_tool(fn_name, conversation):
                logger.warning("Blocked tool '%s' because the student did not explicitly request that integration.", fn_name)
                result = json.dumps({"error": SENSITIVE_TOOL_ERROR})
            else:
                try:
                    result = execute_tool(fn_name, fn_args, cfg)
                except Exception:
                    logger.exception("Tool '%s' crashed unexpectedly", fn_name)
                    result = json.dumps({"error": "Tool execution failed unexpectedly. Analyze the error and try a different approach."})

            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": _truncate_tool_output(result),
                }
            )

    return "I hit the tool call limit. Could you rephrase your question?"


def chat_stream(
    cfg: ConfigDict,
    messages: list[ChatMessage],
    *,
    client: OpenAI | None = None,
    on_token: Any | None = None,
) -> str:
    """Stream the LLM response, calling on_token(text) for each chunk.

    Handles tool calls internally (non-streamed), then streams the final reply.
    Falls back to non-streaming chat() if streaming fails.
    """
    if client is None:
        client = create_client(cfg)

    model = str(cfg.get("model", DEFAULT_MODEL))
    tools = get_all_tools(cfg)
    conversation: list[ChatMessage] = list(messages)

    if not conversation or conversation[0].get("role") != "system":
        system_prompt = build_system_prompt(cfg)
        conversation = [{"role": "system", "content": system_prompt}, *conversation]

    if len(conversation) > MAX_HISTORY + 1:
        conversation = [conversation[0], *conversation[-MAX_HISTORY:]]

    for _ in range(MAX_TOOL_ROUNDS):
        try:
            stream = client.chat.completions.create(
                model=model,
                messages=conversation,
                tools=tools if tools else None,
                stream=True,
            )
        except Exception:
            logger.warning("Streaming failed, falling back to non-streaming", exc_info=True)
            return chat(cfg, messages, client=client)

        collected_content: list[str] = []
        tool_calls_data: dict[int, dict[str, Any]] = {}

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            # Collect text content
            if delta.content:
                collected_content.append(delta.content)
                if on_token:
                    on_token(delta.content)

            # Collect tool call deltas
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_data:
                        tool_calls_data[idx] = {
                            "id": tc_delta.id or "",
                            "name": "",
                            "arguments": "",
                        }
                    if tc_delta.id:
                        tool_calls_data[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tool_calls_data[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tool_calls_data[idx]["arguments"] += tc_delta.function.arguments

        # If we got text content and no tool calls, we're done
        if collected_content and not tool_calls_data:
            return "".join(collected_content)

        # If no tool calls, return whatever we have
        if not tool_calls_data:
            return "".join(collected_content) if collected_content else ""

        # Process tool calls (same as non-streaming)
        assistant_msg: ChatMessage = {"role": "assistant", "content": "".join(collected_content) or None}
        tc_list = []
        for idx in sorted(tool_calls_data):
            tc = tool_calls_data[idx]
            tc_list.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            })
        assistant_msg["tool_calls"] = tc_list
        conversation.append(assistant_msg)

        for tc in tc_list:
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"]["arguments"])
                if not isinstance(fn_args, dict):
                    fn_args = {}
            except (json.JSONDecodeError, TypeError):
                fn_args = {}

            fn_args = _cast_tool_args(fn_args, tools, fn_name)

            if not _user_explicitly_requested_tool(fn_name, conversation):
                result = json.dumps({"error": SENSITIVE_TOOL_ERROR})
            else:
                try:
                    result = execute_tool(fn_name, fn_args, cfg)
                except Exception:
                    logger.exception("Tool '%s' crashed", fn_name)
                    result = json.dumps({"error": "Tool execution failed. Try a different approach."})

            conversation.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": _truncate_tool_output(result),
            })

    return "I hit the tool call limit. Could you rephrase your question?"
