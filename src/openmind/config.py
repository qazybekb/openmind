"""Manage the OpenMind config file in `~/.openmind`."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final, TypeAlias

ConfigDict: TypeAlias = dict[str, Any]

logger = logging.getLogger(__name__)

CONFIG_DIR: Final[Path] = Path.home() / ".openmind"
CONFIG_FILE: Final[Path] = CONFIG_DIR / "config.json"
GMAIL_CREDS_DIR: Final[Path] = CONFIG_DIR / "gmail"
PROFILE_FILE: Final[Path] = CONFIG_DIR / "profile.json"

REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "canvas_token",
    "canvas_url",
    "openrouter_api_key",
    "model",
)

# Only allow Canvas requests to known Berkeley domains
ALLOWED_CANVAS_HOSTS: Final[tuple[str, ...]] = (
    "bcourses.berkeley.edu",
)


def validate_canvas_url(url: str) -> bool:
    """Check that a Canvas URL points to a trusted Berkeley host."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    return host in ALLOWED_CANVAS_HOSTS


def config_exists() -> bool:
    """Return whether the config file exists on disk."""
    return CONFIG_FILE.exists()


def load_config() -> ConfigDict:
    """Load config from disk and return an empty dict when it is missing or invalid."""
    if not CONFIG_FILE.exists():
        return {}

    try:
        raw_config = CONFIG_FILE.read_text(encoding="utf-8")
        data = json.loads(raw_config)
    except OSError:
        logger.warning("Failed to read config from %s", CONFIG_FILE, exc_info=True)
        return {}
    except json.JSONDecodeError:
        logger.warning("Failed to parse config from %s", CONFIG_FILE, exc_info=True)
        return {}

    if not isinstance(data, dict):
        logger.warning("Ignoring config because the root JSON value is not an object.")
        return {}

    return data


def config_valid(cfg: Mapping[str, Any]) -> bool:
    """Return whether all required config keys are present and non-empty."""
    return all(cfg.get(k) for k in REQUIRED_KEYS)


def save_config(cfg: Mapping[str, Any]) -> None:
    """Write config to disk atomically with restricted permissions."""
    import stat
    import tempfile

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    # Restrict directory to owner only
    os.chmod(CONFIG_DIR, stat.S_IRWXU)

    content = json.dumps(dict(cfg), indent=2, sort_keys=True)

    # Write to temp file then rename — atomic on same filesystem
    fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        tmp = Path(tmp_path)
        tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        tmp.replace(CONFIG_FILE)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
