"""The commands a student actually types."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from openmind import cli, secrets
from openmind.config import config_path
from tests.conftest import handler


@pytest.fixture
def canvas(monkeypatch: pytest.MonkeyPatch):
    """Point every CanvasClient the CLI builds at the synthetic instance."""
    from openmind import canvas as canvas_module

    original = canvas_module.CanvasClient.__init__

    def patched(self, base_url, token, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original(self, base_url, token, **kwargs)

    monkeypatch.setattr(canvas_module.CanvasClient, "__init__", patched)
    monkeypatch.setattr(cli.CanvasClient, "__init__", patched)


@pytest.fixture
def stored_token(home: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide a token without touching the developer's real credential store."""
    monkeypatch.setenv(secrets.ENV_VAR, "fake-token-for-tests")


def run(argv: list[str], capsys) -> tuple[int, str, str]:
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# -- parser --------------------------------------------------------------------


def test_the_help_lists_every_command(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for command in ("setup", "mcp", "doctor", "index", "update-data", "clear", "config"):
        assert command in out


def test_the_version_is_reported(capsys):
    from openmind import __version__

    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert __version__ in capsys.readouterr().out


def test_no_command_is_an_error(capsys):
    with pytest.raises(SystemExit):
        cli.main([])


# -- setup ---------------------------------------------------------------------


def test_setup_stores_courses_and_prints_host_config(home: Path, canvas, monkeypatch, capsys):
    monkeypatch.setenv(secrets.ENV_VAR, "fake-token-for-tests")
    monkeypatch.setattr(secrets, "set_token", lambda token, allow_file=False: "keyring")

    code, out, _ = run(["setup", "--all-courses"], capsys)
    assert code == 0

    saved = json.loads(config_path().read_text(encoding="utf-8"))
    assert set(saved["courses"]) == {"1001", "1002", "9999"}
    assert saved["time_zone"] == "America/Los_Angeles"
    assert saved["user_name"] == "Test Student"

    assert "Connected as Test Student" in out
    assert "claude_desktop_config.json" in out
    assert "claude mcp add" in out
    assert "cursor" in out.lower() and "mcp.json" in out
    assert "ChatGPT desktop" in out


def test_setup_never_prints_the_token(home: Path, canvas, monkeypatch, capsys):
    monkeypatch.setenv(secrets.ENV_VAR, "1234~VerySecretTokenValue")
    monkeypatch.setattr(secrets, "set_token", lambda token, allow_file=False: "keyring")
    _, out, err = run(["setup", "--all-courses"], capsys)
    assert "1234~VerySecretTokenValue" not in out + err
    assert "1234~V****alue" in out


def test_setup_says_that_materials_are_not_stored_by_default(home: Path, canvas, monkeypatch, capsys):
    monkeypatch.setenv(secrets.ENV_VAR, "t")
    monkeypatch.setattr(secrets, "set_token", lambda token, allow_file=False: "keyring")
    _, out, _ = run(["setup", "--all-courses"], capsys)
    assert "NOT stored locally unless you ask" in out


def test_setup_warns_loudly_when_a_token_lands_in_a_file(home: Path, canvas, monkeypatch, capsys):
    monkeypatch.setenv(secrets.ENV_VAR, "t")
    monkeypatch.setattr(secrets, "set_token", lambda token, allow_file=False: "file")
    _, _, err = run(["setup", "--all-courses", "--allow-file-secrets"], capsys)
    assert "WARNING" in err and "0600" in err


def test_setup_fails_cleanly_on_a_bad_token(home: Path, monkeypatch, capsys):
    from openmind import canvas as canvas_module

    original = canvas_module.CanvasClient.__init__

    def unauthorized(self, base_url, token, **kwargs):
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(401, json={}, request=request)
        )
        original(self, base_url, token, **kwargs)

    monkeypatch.setattr(cli.CanvasClient, "__init__", unauthorized)
    monkeypatch.setenv(secrets.ENV_VAR, "bad")
    code, _, err = run(["setup"], capsys)
    assert code == 1
    assert "invalid or expired" in err
    assert not config_path().exists()


# -- mcp -----------------------------------------------------------------------


def test_the_host_snippet_is_valid_json_and_carries_no_secret(home: Path, capsys):
    code, out, _ = run(["mcp"], capsys)
    assert code == 0
    block = out[out.index("{") : out.rindex("}") + 1]
    parsed = json.loads(block)
    assert "openmind" in parsed["mcpServers"]
    assert parsed["mcpServers"]["openmind"]["command"]
    assert "token" not in block.lower()


def test_the_host_snippet_uses_an_absolute_path(home: Path, capsys):
    _, out, _ = run(["mcp"], capsys)
    block = json.loads(out[out.index("{") : out.rindex("}") + 1])
    assert Path(block["mcpServers"]["openmind"]["command"]).is_absolute()


# -- doctor --------------------------------------------------------------------


def test_doctor_without_a_config_names_the_setup_command(home: Path, capsys):
    code, _, err = run(["doctor"], capsys)
    assert code == 1
    assert "openmind setup" in err


def test_doctor_checks_the_whole_setup(config, canvas, stored_token, sample_catalog, capsys):
    code, out, _ = run(["doctor"], capsys)
    assert code == 0
    assert "connected as Test Student" in out
    assert "2/2 enabled course(s) reachable" in out
    assert "FTS5 available: yes" in out
    assert "Materials index: none" in out
    assert "Catalog: 3 courses" in out
    assert "Public data updates: off" in out


def test_doctor_reports_a_course_it_cannot_reach(config, stored_token, sample_catalog, monkeypatch, capsys):
    from openmind import canvas as canvas_module

    original = canvas_module.CanvasClient.__init__

    def flaky(self, base_url, token, **kwargs):
        def responder(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/courses/1002"):
                return httpx.Response(403, json={}, request=request)
            return handler(request)

        kwargs["transport"] = httpx.MockTransport(responder)
        original(self, base_url, token, **kwargs)

    monkeypatch.setattr(cli.CanvasClient, "__init__", flaky)
    code, out, err = run(["doctor"], capsys)
    assert code == 1
    assert "NLP (1002)" in err
    assert "1/2 enabled course(s) reachable" in out


def test_doctor_says_the_catalog_is_missing_rather_than_crashing(config, canvas, stored_token, capsys):
    code, _, err = run(["doctor"], capsys)
    assert code == 1
    assert "openmind update-data" in err


# -- config --------------------------------------------------------------------


def test_config_prints_settings_with_the_token_masked(config, stored_token, capsys):
    code, out, _ = run(["config"], capsys)
    assert code == 0
    assert "fake-token-for-tests" not in out
    assert "America/Los_Angeles" in out
    assert "Causal Inference" in out
    assert "[not indexed]" in out


def test_config_can_change_the_two_settings_it_owns(config, capsys):
    assert run(["config", "--set", "capacity_hours_per_day=3.5"], capsys)[0] == 0
    assert json.loads(config_path().read_text())["capacity_hours_per_day"] == 3.5

    assert run(["config", "--set", "data_updates=true"], capsys)[0] == 0
    assert json.loads(config_path().read_text())["data_updates"] is True


def test_config_refuses_to_set_anything_else(config, capsys):
    code, _, err = run(["config", "--set", "canvas_url=https://evil.test"], capsys)
    assert code == 1
    assert "Only capacity_hours_per_day and data_updates" in err
    assert "evil.test" not in config_path().read_text()


def test_config_rejects_a_non_numeric_capacity(config, capsys):
    code, _, err = run(["config", "--set", "capacity_hours_per_day=lots"], capsys)
    assert code == 1
    assert "must be a number" in err


# -- index ---------------------------------------------------------------------


def test_index_builds_a_course_index(config, canvas, stored_token, capsys):
    code, out, _ = run(["index", "--course", "1001"], capsys)
    assert code == 0
    assert "indexed" in out
    assert (config.path.parent / "index.db").exists()


def test_index_refuses_a_course_that_was_not_shared(config, canvas, stored_token, capsys):
    code, _, err = run(["index", "--course", "9999"], capsys)
    assert code == 1
    assert "not one of your enabled courses" in err


def test_index_delete_removes_the_course(config, canvas, stored_token, capsys):
    run(["index", "--course", "1001"], capsys)
    code, out, _ = run(["index", "--course", "1001", "--delete"], capsys)
    assert code == 0
    assert "Deleted the local index" in out


# -- update-data ---------------------------------------------------------------


def test_update_data_can_rebuild_from_the_packaged_snapshot(config, capsys):
    code, out, _ = run(["update-data", "--rebuild"], capsys)
    assert code == 0
    assert "Rebuilt the catalog" in out
    assert (config.path.parent / "catalog.db").exists()


def test_update_data_respects_the_off_switch(config, sample_catalog, capsys):
    code, out, _ = run(["update-data"], capsys)
    assert code == 0
    assert "turned off in your config" in out


# -- clear ---------------------------------------------------------------------


def test_clear_removes_the_materials_index_only(config, canvas, stored_token, sample_catalog, capsys):
    run(["index", "--course", "1001"], capsys)
    code, out, _ = run(["clear", "--yes"], capsys)
    assert code == 0
    assert "Deleted the course materials index" in out
    assert not (config.path.parent / "index.db").exists()
    assert (config.path.parent / "catalog.db").exists()
    assert config_path().exists()


def test_clear_all_removes_config_catalog_and_token(config, sample_catalog, monkeypatch, capsys):
    deleted: list[str] = []
    monkeypatch.setattr(secrets, "delete_token", lambda: deleted.append("token"))

    code, out, _ = run(["clear", "--all", "--yes"], capsys)
    assert code == 0
    assert not config_path().exists()
    assert not (config.path.parent / "catalog.db").exists()
    assert deleted == ["token"]
    assert "bCourses account is untouched" in out


def test_clear_says_what_it_will_delete_before_doing_it(config, capsys):
    _, out, _ = run(["clear", "--yes"], capsys)
    assert "This will delete: the course materials index" in out


# -- nicknames -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "code", "expected"),
    [
        ("STAT 156 - Causal Inference", "STAT 156", "Causal Inference"),
        ("Causal Inference", "STAT 156", "Causal Inference"),
        ("", "STAT 156", "STAT 156"),
        ("x" * 60, "C", "x" * 40),
    ],
)
def test_course_nicknames_are_readable(name: str, code: str, expected: str):
    assert cli._nickname(name, code) == expected


# -- Windows console -----------------------------------------------------------


def test_the_console_is_switched_to_utf8_before_anything_prints(monkeypatch, capsys):
    """A legacy Windows console is cp1252, and this CLI prints em dashes."""
    seen: list[dict] = []

    class FakeStream:
        def reconfigure(self, **kwargs):
            seen.append(kwargs)

    monkeypatch.setattr(cli.sys, "stdout", FakeStream())
    monkeypatch.setattr(cli.sys, "stderr", FakeStream())
    cli._use_utf8()

    assert seen == [{"encoding": "utf-8", "errors": "replace"}] * 2


def test_a_stream_that_cannot_be_reconfigured_is_not_fatal(monkeypatch):
    class Stubborn:
        def reconfigure(self, **kwargs):
            raise ValueError("detached")

    monkeypatch.setattr(cli.sys, "stdout", Stubborn())
    monkeypatch.setattr(cli.sys, "stderr", object())
    cli._use_utf8()  # must not raise


# -- lazy catalog build ---------------------------------------------------------


def test_update_data_builds_the_catalog_on_a_fresh_home(config, capsys):
    """It used to report "already up to date" and build nothing, leaving no catalog at all."""
    from openmind.config import catalog_db_path

    assert not catalog_db_path().exists()
    code, out, _ = run(["update-data"], capsys)

    assert code == 0
    assert "Built the catalog from packaged data" in out
    assert catalog_db_path().exists()


def test_a_second_update_data_run_does_not_rebuild(config, sample_catalog, capsys):
    code, out, _ = run(["update-data"], capsys)
    assert code == 0
    assert "Built the catalog" not in out
    assert "turned off in your config" in out
