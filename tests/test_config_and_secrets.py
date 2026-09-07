"""Config loading, course gating, and where the Canvas token is allowed to live."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from openmind import secrets
from openmind.config import (
    CANVAS_URL,
    Config,
    ConfigError,
    config_path,
    home_dir,
    load_config,
    save_config,
    validate_canvas_url,
)

# -- config --------------------------------------------------------------------


def test_home_follows_the_environment_override(home: Path):
    assert home_dir() == home
    assert config_path() == home / "config.json"


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://bcourses.berkeley.edu", True),
        ("https://bcourses.berkeley.edu.", True),
        ("http://bcourses.berkeley.edu", False),
        ("https://canvas.instructure.com", False),
        ("https://bcourses.berkeley.edu.evil.test", False),
        ("https://evil.test/bcourses.berkeley.edu", False),
        ("", False),
    ],
)
def test_only_bcourses_over_https_is_a_permitted_host(url: str, allowed: bool):
    assert validate_canvas_url(url) is allowed


def test_a_missing_config_is_an_actionable_error(home: Path):
    with pytest.raises(ConfigError, match="openmind setup"):
        load_config(required=True)
    assert load_config().courses == {}


def test_invalid_json_names_the_file(home: Path):
    config_path().write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config()


def test_config_round_trips_through_disk(config: Config):
    reloaded = load_config(required=True)
    assert reloaded.courses == {"1001": "Causal Inference", "1002": "NLP"}
    assert reloaded.time_zone == "America/Los_Angeles"
    assert reloaded.canvas_url == CANVAS_URL
    assert reloaded.capacity_hours_per_day == 2.0
    assert reloaded.data_updates is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_the_config_file_is_owner_only(config: Config):
    mode = stat.S_IMODE(config_path().stat().st_mode)
    assert mode == 0o600


def test_saving_is_atomic_and_leaves_no_temporary_files(home: Path):
    save_config({"courses": {"1": "A"}})
    assert json.loads(config_path().read_text())["courses"] == {"1": "A"}
    assert [p.name for p in home.iterdir() if p.suffix == ".tmp"] == []


def test_a_course_the_student_did_not_share_is_refused_by_name(config: Config):
    with pytest.raises(ConfigError) as excinfo:
        config.require_enabled("9999")
    message = str(excinfo.value)
    assert "9999" in message and "1001" in message and "list_courses" in message


def test_index_flags_never_outlive_the_course_that_was_removed(config: Config):
    config.set("index_enabled", ["1001", "4242"])
    assert config.indexed_course_ids == ("1001",)


def test_a_nonsense_capacity_falls_back_to_the_default(config: Config):
    for bad in ("abc", -1, 0, 500, None):
        config.set("capacity_hours_per_day", bad)
        assert config.capacity_hours_per_day == 2.0
    config.set("capacity_hours_per_day", 3.5)
    assert config.capacity_hours_per_day == 3.5


def test_a_config_naming_a_foreign_canvas_is_rejected(home: Path):
    cfg = Config({"canvas_url": "https://canvas.instructure.com"})
    with pytest.raises(ConfigError, match="not a permitted"):
        _ = cfg.canvas_url


# -- secrets -------------------------------------------------------------------


class FakeKeyring:
    """An in-memory stand-in for the OS credential store."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, account: str) -> str | None:
        return self.store.get((service, account))

    def set_password(self, service: str, account: str, value: str) -> None:
        self.store[(service, account)] = value

    def delete_password(self, service: str, account: str) -> None:
        self.store.pop((service, account), None)

    def get_keyring(self):
        return self


@pytest.fixture
def fake_keyring(monkeypatch: pytest.MonkeyPatch) -> FakeKeyring:
    import sys

    fake = FakeKeyring()
    monkeypatch.setitem(sys.modules, "keyring", fake)
    monkeypatch.setattr(secrets, "keyring_available", lambda: True)
    return fake


TOKEN = "1234~SuperSecretCanvasToken0987654321"


def test_a_token_round_trips_through_the_credential_store(home: Path, fake_keyring: FakeKeyring):
    assert secrets.set_token(TOKEN) == "keyring"
    assert secrets.get_token() == TOKEN
    assert (home / "token").exists() is False
    assert secrets.delete_token() is True
    assert secrets.get_token() is None
    assert secrets.delete_token() is False, "nothing left to delete the second time"


def test_the_environment_variable_wins_over_the_store(home: Path, fake_keyring: FakeKeyring,
                                                      monkeypatch: pytest.MonkeyPatch):
    secrets.set_token(TOKEN)
    monkeypatch.setenv(secrets.ENV_VAR, "env-token")
    assert secrets.get_token() == "env-token"
    assert secrets.backend_name().startswith("environment")


def test_without_a_credential_store_a_file_needs_explicit_permission(home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(secrets, "keyring_available", lambda: False)
    with pytest.raises(secrets.SecretError, match="--allow-file-secrets"):
        secrets.set_token(TOKEN)
    assert secrets.set_token(TOKEN, allow_file=True) == "file"
    assert secrets.get_token() == TOKEN


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_the_file_fallback_is_owner_only(home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(secrets, "keyring_available", lambda: False)
    secrets.set_token(TOKEN, allow_file=True)
    assert stat.S_IMODE((home / "token").stat().st_mode) == 0o600


def test_an_empty_token_is_never_stored(home: Path, fake_keyring: FakeKeyring):
    with pytest.raises(secrets.SecretError):
        secrets.set_token("   ")


def test_masking_never_shows_a_whole_token():
    masked = secrets.mask(TOKEN)
    assert TOKEN not in masked
    assert masked.startswith("1234~S") and masked.endswith("4321")
    assert secrets.mask("short") == "sho****"


def test_the_token_never_appears_in_a_log_line(home: Path, fake_keyring: FakeKeyring, caplog):
    """A token in a log file is a token in a bug report."""
    import logging

    caplog.set_level(logging.DEBUG)
    secrets.set_token(TOKEN)
    secrets.get_token()
    secrets.backend_name()
    secrets.delete_token()
    assert TOKEN not in caplog.text
