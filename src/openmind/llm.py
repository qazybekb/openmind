"""Call the configured LLM through OpenRouter and execute tools."""

from __future__ import annotations

import json
import logging
from typing import Any, Final, TypeAlias

from openai import OpenAI

from openmind.config import ConfigDict
from openmind.personality import build_system_prompt
from openmind.tools import execute_tool, get_all_tools

logger = logging.getLogger(__name__)

ChatMessage: TypeAlias = dict[str, Any]

DEFAULT_MODEL: Final[str] = "google/gemini-2.5-pro"
MAX_TOOL_ROUNDS: Final[int] = 10
MAX_HISTORY: Final[int] = 40
OPENROUTER_API_BASE: Final[str] = "https://openrouter.ai/api/v1"
OPENROUTER_TIMEOUT_S: Final[float] = 60.0


def create_client(cfg: ConfigDict) -> OpenAI:
    """Create an OpenAI-compatible client pointed at OpenRouter."""
    return OpenAI(
        base_url=OPENROUTER_API_BASE,
        api_key=str(cfg.get("openrouter_api_key", "")),
        timeout=OPENROUTER_TIMEOUT_S,
    )


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
        response = client.chat.completions.create(
            model=model,
            messages=conversation,
            tools=tools if tools else None,
        )

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

            try:
                result = execute_tool(fn_name, fn_args, cfg)
            except Exception:
                logger.exception("Tool '%s' crashed unexpectedly", fn_name)
                result = json.dumps({"error": "Tool execution failed unexpectedly."})

            conversation.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return "I hit the tool call limit. Could you rephrase your question?"
