"""Writing a host's config for the student, without touching anything else in it.

Every write here goes through OPENMIND_HOST_CONFIG_DIR, which the fixture redirects.
Nothing in this suite may go near a real Claude or Cursor config.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from openmind import cli, hosts

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="Windows-only launcher layout")


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
    """`cli.shutil` is the stdlib module itself, so a blind stub answers for every
    lookup in the process — including the one that finds this install's launcher. Only
    `claude` is missing here."""
    real_which = shutil.which
    monkeypatch.setattr(
        cli.shutil, "which",
        lambda name, *args, **kwargs: None if name == "claude" else real_which(name, *args, **kwargs),
    )

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


def test_doctor_reports_a_stale_entry_pointing_at_another_install(host_dir: Path, tmp_path: Path, capsys):
    """An upgrade that moved the binary leaves the host silently talking to nothing.

    The old install has to be runnable, or doctor rightly reports the simpler fault
    instead. `SCRIPT_NAMES[0]` carries the extension Windows needs to consider a file
    executable at all; the mode bit is what POSIX asks for.
    """
    other = tmp_path / "old-install" / hosts.SCRIPT_NAMES[0]
    other.parent.mkdir()
    other.write_text("#!/bin/sh\n", encoding="utf-8")
    other.chmod(0o755)
    hosts.cursor_path().write_text(
        json.dumps({"mcpServers": {"openmind": {"command": str(other)}}}), encoding="utf-8"
    )

    code, out, _ = run(["doctor"], capsys)

    assert "but this install is" in out
    assert code == 1


def test_host_status_is_none_for_hosts_without_a_config_file(host_dir: Path):
    assert hosts.status(hosts.find("chatgpt")) is None
    assert hosts.status(hosts.find("claude-code")) is None


# -- resolving this install's launcher ---------------------------------------------


@pytest.fixture
def fake_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An interpreter with an `openmind-mcp` beside it, and nothing useful on PATH.

    The launcher is named the way this platform names it — `openmind-mcp.exe` on
    Windows — because an install that Windows cannot execute is not an install.
    """
    bin_dir = tmp_path / "install" / "bin"
    bin_dir.mkdir(parents=True)
    interpreter = bin_dir / "python"
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    interpreter.chmod(0o755)
    script = bin_dir / hosts.SCRIPT_NAMES[0]
    script.write_text("#!/bin/sh\nexec python -m openmind.server\n", encoding="utf-8")
    script.chmod(0o755)

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(hosts.sys, "executable", str(interpreter))
    monkeypatch.setattr(hosts.sys, "argv", [str(bin_dir / "openmind")])
    monkeypatch.setenv("PATH", str(empty))
    return script


@pytest.fixture
def no_install(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An interpreter with no launcher anywhere: not beside it, not on PATH."""
    bin_dir = tmp_path / "bare" / "bin"
    bin_dir.mkdir(parents=True)
    interpreter = bin_dir / "python"
    interpreter.write_text("#!/bin/sh\n", encoding="utf-8")
    interpreter.chmod(0o755)

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(hosts.sys, "executable", str(interpreter))
    monkeypatch.setattr(hosts.sys, "argv", [str(bin_dir / "openmind")])
    monkeypatch.setenv("PATH", str(empty))


def test_the_launcher_is_found_beside_the_interpreter_when_path_is_empty(fake_install: Path):
    """A host does not inherit PATH, and neither does an IDE terminal."""
    assert hosts.find_server_script() == fake_install
    assert hosts.command_line() == str(fake_install)


def test_a_symlinked_interpreter_is_not_followed_to_its_target(tmp_path: Path, monkeypatch):
    """Resolving the venv symlink lands on a base interpreter with no openmind at all."""
    real_bin = tmp_path / "base" / "bin"
    real_bin.mkdir(parents=True)
    (real_bin / "python3").write_text("#!/bin/sh\n", encoding="utf-8")
    (real_bin / "python3").chmod(0o755)

    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python").symlink_to(real_bin / "python3")
    script = venv_bin / hosts.SCRIPT_NAMES[0]
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(hosts.sys, "executable", str(venv_bin / "python"))
    monkeypatch.setattr(hosts.sys, "argv", [str(venv_bin / "openmind")])
    monkeypatch.setenv("PATH", str(empty))

    assert hosts.find_server_script() == script
    assert str(real_bin) not in hosts.command_line()


def test_a_directory_entry_named_like_the_script_is_not_mistaken_for_it(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / hosts.SCRIPT_NAMES[0]).mkdir()

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(hosts.sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(hosts.sys, "argv", [str(bin_dir / "openmind")])
    monkeypatch.setenv("PATH", str(empty))

    assert hosts.find_server_script() is None


def test_a_non_executable_script_is_not_offered_to_a_host(tmp_path: Path, monkeypatch):
    """A file the operating system will not run is not a launcher.

    Each platform is asked in its own terms: POSIX reads the mode bit, and Windows —
    where every readable file passes `os.access(X_OK)` — reads the extension, and an
    `openmind-mcp` with no extension is not something it can execute.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "python").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "openmind-mcp").write_text("#!/bin/sh\n", encoding="utf-8")
    (bin_dir / "openmind-mcp").chmod(0o644)

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(hosts.sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(hosts.sys, "argv", [str(bin_dir / "openmind")])
    monkeypatch.setenv("PATH", str(empty))

    assert hosts.find_server_script() is None


def test_executability_is_decided_the_way_this_platform_decides_it(tmp_path: Path):
    """The one rule the rest of this file leans on, stated directly."""
    script = tmp_path / hosts.SCRIPT_NAMES[0]
    script.write_text("#!/bin/sh\n", encoding="utf-8")
    script.chmod(0o755)
    assert hosts.is_executable(script)

    plain = tmp_path / "notes.txt"
    plain.write_text("hello\n", encoding="utf-8")
    plain.chmod(0o644)
    assert not hosts.is_executable(plain), "a text file is not a launcher on any platform"

    assert not hosts.is_executable(tmp_path), "a directory is not a launcher"
    assert not hosts.is_executable(tmp_path / "absent")


@WINDOWS_ONLY
def test_the_launcher_is_found_in_the_scripts_directory_below_the_interpreter(tmp_path: Path, monkeypatch):
    """A Windows install puts `python.exe` at the root of the prefix and the console
    scripts in `Scripts` below it, so looking only beside the interpreter finds nothing."""
    prefix = tmp_path / "prefix"
    (prefix / "Scripts").mkdir(parents=True)
    (prefix / "python.exe").write_text("", encoding="utf-8")
    script = prefix / "Scripts" / "openmind-mcp.exe"
    script.write_text("", encoding="utf-8")

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(hosts.sys, "executable", str(prefix / "python.exe"))
    monkeypatch.setattr(hosts.sys, "argv", [str(prefix / "Scripts" / "openmind")])
    monkeypatch.setenv("PATH", str(empty))

    assert hosts.find_server_script() == script


def test_the_missing_launcher_error_names_where_it_looked(no_install):
    with pytest.raises(hosts.HostError) as excinfo:
        hosts.command_line()

    message = str(excinfo.value)
    assert "uv tool install openmind-berkeley" in message
    for directory in hosts.searched_directories():
        assert str(directory) in message


def test_writing_refuses_when_the_launcher_cannot_be_found(host_dir: Path, no_install, capsys):
    """A config naming a launcher that does not exist fails silently inside the host."""
    code, _, err = run(["mcp", "--write", "claude-desktop", "--yes"], capsys)

    assert code == 1
    assert "Could not find the `openmind-mcp` launcher" in err
    assert not hosts.claude_desktop_path().exists()
    assert list(host_dir.glob("*.bak")) == []


def test_a_refused_write_leaves_an_existing_config_untouched(host_dir: Path, no_install, capsys):
    before = json.dumps({"mcpServers": {"other": {"command": "/bin/true"}}}, indent=2)
    hosts.cursor_path().write_text(before, encoding="utf-8")

    code, _, err = run(["mcp", "--write", "cursor", "--yes"], capsys)

    assert code == 1
    assert "Could not find" in err
    assert hosts.cursor_path().read_text(encoding="utf-8") == before
    assert list(host_dir.glob("*.bak")) == []


def test_printing_the_snippet_refuses_too_rather_than_naming_a_dead_path(host_dir: Path, no_install, capsys):
    code, out, err = run(["mcp"], capsys)

    assert code == 1
    assert "Could not find" in err
    assert "mcpServers" not in out


def test_the_written_command_is_the_sibling_script_not_a_module_fallback(host_dir: Path, fake_install: Path, capsys):
    """`python -m openmind.server` on a base interpreter cannot import the server."""
    code, _, _ = run(["mcp", "--write", "claude-desktop", "--yes"], capsys)

    assert code == 0
    written = json.loads(hosts.claude_desktop_path().read_text(encoding="utf-8"))["mcpServers"]["openmind"]
    assert written == {"command": str(fake_install)}
    assert "args" not in written


def test_doctor_calls_a_sibling_script_entry_current_even_with_an_empty_path(host_dir: Path, fake_install: Path,
                                                                            capsys):
    """The old comparison was against a formatted string, so a correct entry read as stale."""
    hosts.claude_desktop_path().write_text(
        json.dumps({"mcpServers": {"openmind": {"command": str(fake_install)}}}), encoding="utf-8"
    )

    _, out, _ = run(["doctor"], capsys)

    assert "Claude Desktop: configured and current" in out


def test_doctor_reports_a_missing_launcher(host_dir: Path, no_install, capsys):
    code, _, err = run(["doctor"], capsys)

    assert code == 1
    assert "was not found next to this install" in err
    assert "uv tool install openmind-berkeley" in err


def test_an_entry_reached_by_a_different_but_equivalent_path_is_current(host_dir: Path, fake_install: Path,
                                                                       tmp_path: Path, capsys):
    """A symlinked bin directory is the same install, not a stale one."""
    alias = tmp_path / "alias"
    alias.symlink_to(fake_install.parent)
    hosts.claude_desktop_path().write_text(
        json.dumps({"mcpServers": {"openmind": {"command": str(alias / fake_install.name)}}}), encoding="utf-8"
    )

    _, out, _ = run(["doctor"], capsys)

    assert "configured and current" in out


def test_claude_code_registration_uses_the_resolved_script(host_dir: Path, fake_install: Path, monkeypatch, capsys):
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr(cli.shutil, "which", lambda name: "/usr/local/bin/claude")
    import subprocess

    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd) or Result())

    run(["mcp", "--write", "claude-code", "--yes"], capsys)

    assert calls[0][-1] == str(fake_install)
