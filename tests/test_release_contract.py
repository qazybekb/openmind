"""What the server promises: 12 tools, 5 prompts, honest docs, silent stdout."""

from __future__ import annotations

import io
import re
import sys
import tomllib
from contextlib import redirect_stdout
from pathlib import Path

import anyio
import pytest
from mcp.client import Client

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOLS = {
    "list_courses", "get_deadlines", "get_assignment", "get_course_overview", "get_grades",
    "find_materials", "read_material", "index_course", "prepare_study_session",
    "search_catalog", "get_catalog_course", "check_offering",
}
EXPECTED_PROMPTS = {"tutor", "practice", "weekly_plan", "explain_assignment", "course_planner"}

WRITE_WORDS = re.compile(r"\b(submit|upload|post|send|delete|create|update|write|enroll|drop|message|email)\b", re.I)


def describe():
    """Ask the server to describe itself the way a host does."""
    from openmind.server import mcp

    async def run():
        async with Client(mcp) as client:
            return await client.list_tools(), await client.list_prompts()

    return anyio.run(run)


@pytest.fixture(scope="module")
def described():
    return describe()


# -- surface -------------------------------------------------------------------


def test_the_server_exposes_exactly_twelve_tools(described):
    tools, _ = described
    assert {tool.name for tool in tools.tools} == EXPECTED_TOOLS
    assert len(tools.tools) == 12


def test_the_server_exposes_exactly_five_prompts(described):
    _, prompts = described
    assert {prompt.name for prompt in prompts.prompts} == EXPECTED_PROMPTS


def test_every_tool_has_a_title_and_a_description_a_model_can_route_on(described):
    tools, _ = described
    for tool in tools.tools:
        assert tool.title, f"{tool.name} has no title"
        assert tool.description and len(tool.description) > 60, f"{tool.name} has a thin description"


def test_only_index_course_is_declared_as_writing_anything(described):
    tools, _ = described
    for tool in tools.tools:
        assert tool.annotations is not None, f"{tool.name} has no annotations"
        read_only = tool.annotations.read_only_hint
        assert read_only is (tool.name != "index_course"), f"{tool.name}: read_only_hint={read_only}"
        if tool.name == "index_course":
            assert tool.annotations.destructive_hint is False


def test_no_tool_offers_a_way_to_change_anything_in_bcourses(described):
    """The read-only promise has to hold at the surface, not just in the client."""
    tools, _ = described
    for tool in tools.tools:
        assert not WRITE_WORDS.search(tool.name.replace("_", " ")), tool.name
    assert not {"web_fetch", "run_shell", "submit_assignment", "send_message"} & {t.name for t in tools.tools}


def test_every_tool_parameter_is_documented(described):
    tools, _ = described
    for tool in tools.tools:
        for name, spec in (tool.input_schema.get("properties") or {}).items():
            assert spec.get("description"), f"{tool.name}.{name} has no description"


def test_the_server_instructions_set_the_ground_rules(described):
    from openmind.server import INSTRUCTIONS

    lowered = INSTRUCTIONS.lower()
    for phrase in ("bcourses", "read-only", "due_human", "/answer", "evidence, not instructions", "partial"):
        assert phrase in lowered, f"server instructions do not mention {phrase!r}"
    assert len(INSTRUCTIONS) <= 900


# -- documentation ------------------------------------------------------------


def test_the_tools_reference_documents_every_tool_exactly_once(described):
    tools, _ = described
    text = (REPO_ROOT / "docs" / "TOOLS.md").read_text(encoding="utf-8")
    tools_section = text.split("## Prompts")[0]
    documented = re.findall(r"^\| `([a-z_]+)`", tools_section, flags=re.MULTILINE)
    assert sorted(documented) == sorted(tool.name for tool in tools.tools)
    assert len(documented) == len(set(documented))


def test_the_tools_reference_documents_every_prompt(described):
    _, prompts = described
    text = (REPO_ROOT / "docs" / "TOOLS.md").read_text(encoding="utf-8")
    for prompt in prompts.prompts:
        assert f"`{prompt.name}`" in text, f"{prompt.name} is not in docs/TOOLS.md"


def test_privacy_copy_does_not_claim_more_than_the_code_delivers():
    """The server is local, but the host model is not. Copy must not blur that."""
    disallowed = (
        "all data stays on your machine",
        "api tokens are never transmitted",
        "runs entirely offline",
        "no data ever leaves",
        "on-device ai",
    )
    files = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "docs" / "PRIVACY.md",
        REPO_ROOT / "docs" / "SETUP.md",
        *(REPO_ROOT / "website" / "src").rglob("*.astro"),
    ]
    for path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").lower()
        for phrase in disallowed:
            assert phrase not in text, f"{path.relative_to(REPO_ROOT)} claims: {phrase}"


def test_privacy_doc_names_every_network_destination():
    """Four destinations, each disclosed. A fifth would be a surprise to the student."""
    text = (REPO_ROOT / "docs" / "PRIVACY.md").read_text(encoding="utf-8").lower()
    for host in ("bcourses.berkeley.edu", "classes.berkeley.edu", "github"):
        assert host in text, f"PRIVACY.md does not mention {host}"
    assert "data_updates" in text


def test_distribution_metadata_matches_the_release():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject["project"]
    assert project["name"] == "openmind-berkeley"
    assert project["scripts"] == {"openmind": "openmind.cli:main", "openmind-mcp": "openmind.server:main"}
    assert project["requires-python"] == ">=3.11"

    removed = {"typer", "rich", "prompt-toolkit", "openai", "pymupdf", "python-telegram-bot",
               "google-auth-oauthlib", "google-api-python-client"}
    declared = {re.split(r"[><=~ ;\[]", dep)[0].lower() for dep in project["dependencies"]}
    assert not (declared & removed), f"removed dependencies are back: {declared & removed}"
    assert "mcp" in declared and "pypdf" in declared and "keyring" in declared

    distribution = (REPO_ROOT / "docs" / "DISTRIBUTION.md").read_text(encoding="utf-8")
    assert "openmind-berkeley" in distribution


def test_the_version_is_consistent_across_the_package_and_the_changelog():
    from openmind import __version__

    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__
    assert __version__ in (REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


# -- stdio hygiene -------------------------------------------------------------


def test_importing_the_server_prints_nothing_to_stdout():
    """Anything on stdout corrupts the protocol frame a host is waiting for."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-c", "import openmind.server; import openmind.cli"],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src"),
                                             "HOME": "/tmp"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "", f"the server wrote to stdout on import: {result.stdout!r}"


def test_listing_tools_writes_nothing_to_stdout():
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        describe()
    assert buffer.getvalue() == ""


def test_starting_the_server_makes_no_network_calls_and_reads_no_config(monkeypatch):
    """A host spawns this process on launch; it must not touch Canvas or the disk yet."""
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("the server opened a socket during startup")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)

    from openmind.config import ConfigError

    def refuse(*args, **kwargs):
        raise ConfigError("config must not be read at startup")

    monkeypatch.setattr("openmind.server.load_config", refuse)
    tools, prompts = describe()
    assert len(tools.tools) == 12
    assert len(prompts.prompts) == 5


def test_pypdf_is_not_imported_until_a_document_is_read():
    import subprocess

    result = subprocess.run(
        [sys.executable, "-c", "import sys, openmind.server; print('pypdf' in sys.modules)"],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(REPO_ROOT / "src"), "HOME": "/tmp"},
    )
    assert result.stdout.strip() == "False", "pypdf is imported at startup, slowing every launch"


# -- tool errors ---------------------------------------------------------------


def test_a_tool_called_without_setup_returns_an_actionable_error(home, monkeypatch):
    from openmind.server import mcp

    async def run():
        async with Client(mcp) as client:
            return await client.call_tool("list_courses", {})

    result = anyio.run(run)
    assert result.is_error
    message = " ".join(block.text for block in result.content if hasattr(block, "text"))
    assert "openmind setup" in message


# -- public tools ---------------------------------------------------------------


def test_the_catalog_tools_work_without_a_canvas_account(home, sample_catalog):
    """A student can ask what to take next semester before handing over any credential."""
    from openmind.server import _app, mcp

    _app.close()
    _app._config = None

    async def run():
        async with Client(mcp) as client:
            return (
                await client.call_tool("search_catalog", {"query": "causal inference", "limit": 2}),
                await client.call_tool("get_catalog_course", {"subject": "COMPSCI", "number": "189"}),
                await client.call_tool("list_courses", {}),
            )

    catalog_result, detail_result, canvas_result = anyio.run(run)
    _app.close()
    _app._config = None

    assert not catalog_result.is_error, catalog_result.content[0].text
    assert not detail_result.is_error, detail_result.content[0].text
    assert canvas_result.is_error, "Canvas tools must still require setup"
    assert "openmind setup" in canvas_result.content[0].text
