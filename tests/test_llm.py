"""Tests for the LLM orchestration layer."""

from __future__ import annotations

import types
import unittest
from unittest.mock import MagicMock, patch

from openmind import llm


class _FakeMessage:
    """Minimal chat message stub for tool-calling tests."""

    def __init__(self, *, content: str | None, tool_calls: list[object] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, exclude_none: bool = True) -> dict[str, object]:
        """Return a serializable assistant message payload."""
        del exclude_none
        return {"role": "assistant", "content": self.content}


class _FakeResponse:
    """Minimal OpenAI response stub."""

    def __init__(self, message: _FakeMessage) -> None:
        self.choices = [types.SimpleNamespace(message=message)]


class LlmPolicyTests(unittest.TestCase):
    """Verify tool-call safety checks."""

    def test_recent_explicit_request_allows_sensitive_tool(self) -> None:
        """Allow Gmail access when the student recently asked about email."""
        conversation = [
            {"role": "user", "content": "Summarize my unread emails"},
            {"role": "assistant", "content": "Sure."},
            {"role": "user", "content": "Open the first one"},
        ]
        self.assertTrue(llm._user_explicitly_requested_tool("gmail_read", conversation))

    def test_sensitive_tool_is_blocked_without_explicit_request(self) -> None:
        """Block sensitive integrations when the student asked about something else."""
        conversation = [{"role": "user", "content": "What's due this week?"}]
        self.assertFalse(llm._user_explicitly_requested_tool("gmail_search", conversation))
        self.assertFalse(llm._user_explicitly_requested_tool("obsidian_search", conversation))
        self.assertTrue(llm._user_explicitly_requested_tool("get_upcoming_assignments", conversation))

    def test_chat_blocks_sensitive_tool_when_request_is_not_explicit(self) -> None:
        """Return a policy error instead of executing a blocked tool."""
        tool_call = types.SimpleNamespace(
            id="tool-1",
            function=types.SimpleNamespace(name="gmail_search", arguments='{"query": "from:prof"}'),
        )
        client = types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=MagicMock(
                        side_effect=[
                            _FakeResponse(_FakeMessage(content=None, tool_calls=[tool_call])),
                            _FakeResponse(_FakeMessage(content="Done.", tool_calls=[])),
                        ]
                    )
                )
            )
        )

        with (
            patch("openmind.llm.build_system_prompt", return_value="system"),
            patch("openmind.llm.get_all_tools", return_value=[]),
            patch("openmind.llm.execute_tool") as execute_tool,
            patch.object(llm.logger, "warning"),
        ):
            result = llm.chat({}, [{"role": "user", "content": "What's due this week?"}], client=client)

        self.assertEqual(result, "Done.")
        execute_tool.assert_not_called()


if __name__ == "__main__":
    unittest.main()
