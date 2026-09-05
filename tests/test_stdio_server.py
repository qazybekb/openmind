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
def server(home: Path, sample_catalog: Path) -> StdioServerParameters:
    """Launch parameters pointing at this checkout with an isolated home."""
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "openmind.server"],
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(REPO_ROOT / "src"),
            "OPENMIND_HOME": os.environ["OPENMIND_HOME"],
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
