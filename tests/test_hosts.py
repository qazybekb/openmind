"""Writing a host's config for the student, without touching anything else in it.

Every write here goes through OPENMIND_HOST_CONFIG_DIR, which the fixture redirects.
Nothing in this suite may go near a real Claude or Cursor config.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from openmind import cli, hosts


@pytest.fixture
def host_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every host config path into a temporary directory."""
    target = tmp_path / "hostconfig"
    target.mkdir()
    monkeypatch.setenv(hosts.ENV_OVERRIDE, str(target))
    return target


def run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# -- locating the files ------------------------------------------------------------


def test_the_override_redirects_every_host_path(host_dir: Path):
    assert hosts.claude_desktop_path().parent == host_dir
    assert hosts.cursor_path().parent == host_dir


def test_without_the_override_the_real_platform_paths_are_used(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv(hosts.ENV_OVERRIDE, raising=False)
    assert "Claude" in str(hosts.claude_desktop_path())
    assert hosts.claude_desktop_path().name == "claude_desktop_config.json"
    assert hosts.cursor_path() == Path.home() / ".cursor" / "mcp.json"


def test_the_entry_contains_a_path_and_nothing_else():
    """No token, no home directory, no course ids — only how to start the server."""
    entry = hosts.entry()
    assert set(entry) <= {"command", "args"}
    assert Path(entry["command"]).is_absolute()
    assert "token" not in json.dumps(entry).lower()


def test_every_host_key_resolves():
    for host in hosts.hosts():
        assert hosts.find(host.key) is not None


def test_an_unknown_host_lists_the_real_ones():
    with pytest.raises(hosts.HostError, match="claude-desktop"):
        hosts.find("emacs")


# -- writing -----------------------------------------------------------------------


def test_writing_creates_a_config_when_told_to(host_dir: Path, capsys):
    code, out, _ = run(["mcp", "--write", "claude-desktop", "--yes"], capsys)

    assert code == 0
    document = json.loads(hosts.claude_desktop_path().read_text(encoding="utf-8"))
    assert Path(document["mcpServers"]["openmind"]["command"]).is_absolute()
    assert "Added the openmind entry" in out
    assert "Restart Claude Desktop" in out


def test_creating_a_file_needs_explicit_permission(host_dir: Path, capsys):
    """Writing a new file into someone's application-support directory is not a default."""
    code, out, err = run(["mcp", "--write", "claude-desktop"], capsys)

    assert code == 1
    assert not hosts.claude_desktop_path().exists()
    assert "--yes" in err
    assert "Nothing was written" in out


def test_merging_leaves_other_servers_alone(host_dir: Path, capsys):
    existing = {
        "mcpServers": {"some-other-server": {"command": "/usr/local/bin/other", "args": ["--flag"]}},
        "unrelatedTopLevelKey": True,
    }
    hosts.cursor_path().write_text(json.dumps(existing, indent=2), encoding="utf-8")

    code, _, _ = run(["mcp", "--write", "cursor", "--yes"], capsys)

    assert code == 0
    document = json.loads(hosts.cursor_path().read_text(encoding="utf-8"))
    assert document["mcpServers"]["some-other-server"] == existing["mcpServers"]["some-other-server"]
    assert document["unrelatedTopLevelKey"] is True
    assert "openmind" in document["mcpServers"]


def test_an_existing_config_is_backed_up_before_it_is_touched(host_dir: Path, capsys):
    hosts.cursor_path().write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    _, out, _ = run(["mcp", "--write", "cursor", "--yes"], capsys)

    backups = list(host_dir.glob("cursor_mcp.json.*.bak"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == {"mcpServers": {}}
    assert "Backed up" in out


def test_the_change_is_shown_as_a_diff(host_dir: Path, capsys):
    hosts.cursor_path().write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
    _, out, _ = run(["mcp", "--write", "cursor", "--yes"], capsys)

    assert "--- before" in out and "+++ after" in out
    assert "+" in out and "openmind" in out


def test_writing_twice_changes_nothing_the_second_time(host_dir: Path, capsys):
    run(["mcp", "--write", "cursor", "--yes"], capsys)
    code, out, _ = run(["mcp", "--write", "cursor", "--yes"], capsys)

    assert code == 0
    assert "already points at this install" in out
    assert list(host_dir.glob("*.bak")) == [], "an unchanged config is not backed up again"


def test_a_stale_entry_is_updated_rather_than_duplicated(host_dir: Path, capsys):
    hosts.cursor_path().write_text(
        json.dumps({"mcpServers": {"openmind": {"command": "/old/install/openmind-mcp"}}}), encoding="utf-8"
    )

    code, out, _ = run(["mcp", "--write", "cursor", "--yes"], capsys)

    assert code == 0 and "Updated the openmind entry" in out
    servers = json.loads(hosts.cursor_path().read_text(encoding="utf-8"))["mcpServers"]
    assert len(servers) == 1
    assert servers["openmind"]["command"] != "/old/install/openmind-mcp"


def test_a_config_that_is_not_valid_json_is_refused_not_overwritten(host_dir: Path, capsys):
    """Someone's hand-edited config with a trailing comma is not ours to replace."""
    hosts.cursor_path().write_text('{"mcpServers": {,}}', encoding="utf-8")

    code, _, err = run(["mcp", "--write", "cursor", "--yes"], capsys)

    assert code == 1
    assert "not valid JSON" in err
    assert hosts.cursor_path().read_text(encoding="utf-8") == '{"mcpServers": {,}}'


def test_a_host_without_a_config_file_prints_its_instructions(host_dir: Path, capsys):
    code, out, _ = run(["mcp", "--write", "chatgpt", "--yes"], capsys)

    assert code == 0
    assert "no config file to write" in out
    assert "STDIO" in out


def test_claude_code_is_registered_through_its_own_command(host_dir: Path, monkeypatch, capsys):
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "Added stdio MCP server openmind"
        stderr = ""

    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/local/bin/claude")
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Result())

    code, out, _ = run(["mcp", "--write", "claude-code", "--yes"], capsys)

    assert code == 0
    assert calls[0][:6] == ["claude", "mcp", "add", "--scope", "user", "openmind"]
    assert "Registered with Claude Code" in out


def test_claude_code_without_the_cli_prints_the_command_instead(host_dir: Path, monkeypatch, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)

    code, out, _ = run(["mcp", "--write", "claude-code", "--yes"], capsys)

    assert code == 0
    assert "claude mcp add --scope user openmind --" in out


def test_the_printed_snippets_still_work(host_dir: Path, capsys):
    code, out, _ = run(["mcp"], capsys)

    assert code == 0
    block = json.loads(out[out.index("{") : out.index("}\n\nClaude Code") + 1])
    assert "openmind" in block["mcpServers"]
    assert "openmind mcp --write claude-desktop" in out


# -- doctor -------------------------------------------------------------------------


def test_doctor_reports_a_host_with_no_config(host_dir: Path, capsys):
    _, out, _ = run(["doctor"], capsys)
    assert "Claude Desktop: no config file" in out


def test_doctor_reports_a_configured_host(host_dir: Path, capsys):
    run(["mcp", "--write", "cursor", "--yes"], capsys)
    _, out, _ = run(["doctor"], capsys)
    assert "Cursor: configured and current" in out


def test_doctor_reports_a_config_without_an_openmind_entry(host_dir: Path, capsys):
    hosts.cursor_path().write_text(json.dumps({"mcpServers": {"other": {"command": "/bin/true"}}}), encoding="utf-8")

    code, out, _ = run(["doctor"], capsys)

    assert "has no openmind entry" in out
    assert "openmind mcp --write cursor" in out
    assert code == 1


def test_doctor_reports_an_entry_pointing_at_a_missing_binary(host_dir: Path, capsys):
    hosts.cursor_path().write_text(
        json.dumps({"mcpServers": {"openmind": {"command": "/nonexistent/openmind-mcp"}}}), encoding="utf-8"
    )

    code, out, _ = run(["doctor"], capsys)

    assert "missing or not executable" in out
    assert code == 1


def test_doctor_reports_a_stale_entry_pointing_at_another_install(host_dir: Path, capsys):
    """An upgrade that moved the binary leaves the host silently talking to nothing."""
    hosts.cursor_path().write_text(
        json.dumps({"mcpServers": {"openmind": {"command": "/bin/sh"}}}), encoding="utf-8"
    )

    code, out, _ = run(["doctor"], capsys)

    assert "but this install is" in out
    assert code == 1


def test_host_status_is_none_for_hosts_without_a_config_file(host_dir: Path):
    assert hosts.status(hosts.find("chatgpt")) is None
    assert hosts.status(hosts.find("claude-code")) is None
