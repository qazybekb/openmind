"""Drive the server the way an AI app does: as a subprocess over stdio.

Everything else in the suite talks to the server in-process. This file is the only place
that exercises what a host actually does — spawn a command, write JSON-RPC frames to its
stdin, and read frames back from its stdout. It is what catches a stray print, a slow
import, or a packaging mistake that no in-process test would notice.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import anyio
import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTUP_BUDGET_S = 5.0


@pytest.fixture
def server(home: Path) -> StdioServerParameters:
    """Launch parameters pointing at this checkout with an isolated home."""
    # The spawned process is outside the in-process fixtures, so the file it reads
    # must say what they would: no update check against GitHub during a test.
    (home / "config.json").write_text(json.dumps({"data_updates": False}), encoding="utf-8")
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "openmind.server"],
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "OPENMIND_HOME": os.environ["OPENMIND_HOME"],
            "OPENMIND_CREDENTIAL_STORE": "none",
            "HOME": os.environ.get("HOME", "/tmp"),
            "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        },
    )


def drive(params: StdioServerParameters, work):
    """Run an async block against a freshly spawned server process."""
    async def main():
        async with Client(params) as client:
            return await work(client)

    return anyio.run(main)


def test_a_host_can_connect_and_discover_the_tools(server: StdioServerParameters):
    async def work(client):
        return await client.list_tools(), await client.list_prompts()

    started = time.monotonic()
    tools, prompts = drive(server, work)
    elapsed = time.monotonic() - started

    assert len(tools.tools) == 12
    assert len(prompts.prompts) == 5
    assert elapsed < STARTUP_BUDGET_S, f"connecting took {elapsed:.1f}s; a host will feel that"


def test_the_public_catalog_answers_over_a_real_pipe(server: StdioServerParameters):
    """The whole round trip: JSON-RPC in, SQLite lookup, JSON-RPC out."""
    async def work(client):
        return await client.call_tool("search_catalog", {"query": "causal inference", "limit": 3})

    result = drive(server, work)
    assert not result.is_error, result.content[0].text
    payload = json.loads(result.content[0].text)
    assert payload["courses"][0]["subject"] == "STAT"
    assert payload["catalog_as_of"]
    assert payload["partial"] is False


def test_a_tool_needing_bcourses_fails_with_an_instruction(server: StdioServerParameters):
    async def work(client):
        return await client.call_tool("get_deadlines", {})

    result = drive(server, work)
    assert result.is_error
    assert "openmind setup" in result.content[0].text


def test_an_unknown_tool_is_rejected_rather_than_guessed_at(server: StdioServerParameters):
    async def work(client):
        return await client.call_tool("delete_everything", {})

    result = drive(server, work)
    assert result.is_error


def test_the_server_advertises_its_ground_rules_to_the_host(server: StdioServerParameters):
    """The instructions are how the host learns not to recompute dates or leak evidence."""
    async def work(client):
        return client.instructions, client.server_info

    instructions, server_info = drive(server, work)
    lowered = (instructions or "").lower()
    assert "bcourses" in lowered
    assert "due_human" in lowered
    assert "read-only" in lowered
    assert server_info.name == "openmind"


# -- prompts without a bCourses account -----------------------------------------


@pytest.mark.parametrize(
    ("prompt", "args"),
    [
        ("tutor", {"course": "INFO 205", "topic": "contextual integrity"}),
        ("practice", {"course": "INFO 205", "topic": "contextual integrity"}),
        ("weekly_plan", {}),
        ("explain_assignment", {"course": "INFO 205", "assignment": "Lab 1"}),
    ],
)
def test_a_canvas_prompt_without_a_token_explains_itself_instead_of_failing(
    server: StdioServerParameters, prompt: str, args: dict
):
    """MCP prompts have no error channel: raising gives the host "Error rendering prompt X"."""
    async def work(client):
        return await client.get_prompt(prompt, args)

    result = drive(server, work)  # must not raise
    text = result.messages[0].content.text
    assert "openmind setup" in text
    assert "restart your AI app" in text


def test_the_course_planner_works_without_a_bcourses_account(server: StdioServerParameters):
    """Catalog planning is public data; it should not need a credential."""
    async def work(client):
        return await client.get_prompt("course_planner", {"interests": "causal inference"})

    text = drive(server, work).messages[0].content.text
    assert "STAT 156" in text
    assert "check with your advisor" in text
    assert "bCourses is not connected" in text


def test_a_prompt_needing_setup_logs_no_traceback(server: StdioServerParameters, capfd):
    """A student who has not run setup is an ordinary state, not a fault to report."""
    async def work(client):
        return await client.get_prompt("tutor", {"course": "X", "topic": "y"})

    drive(server, work)
    stderr = capfd.readouterr().err
    assert "Traceback" not in stderr
    assert "Error rendering prompt" not in stderr


def test_the_catalog_builds_itself_over_stdio_without_setup(server: StdioServerParameters, home: Path):
    """First catalog question on a fresh machine: no token, no setup, no rebuild flag."""
    async def work(client):
        return await client.call_tool("search_catalog", {"query": "causal inference", "limit": 10})

    result = drive(server, work)
    assert not result.is_error, result.content[0].text
    payload = json.loads(result.content[0].text)
    assert len(payload["courses"]) == 10
    assert ("STAT", "156") in [(c["subject"], c["number"]) for c in payload["courses"][:3]]
    assert (home / "catalog.db").exists()
