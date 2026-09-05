"""Read and write the non-secret OpenMind MCP configuration.

Everything here is safe to put on disk in the clear: enabled course ids, the student's
Canvas time zone, which courses have a local materials index, and a few preferences.
The Canvas token lives in the OS credential store (see :mod:`openmind.secrets`).
"""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ALLOWED_CANVAS_HOSTS: Final[tuple[str, ...]] = ("bcourses.berkeley.edu",)
CANVAS_URL: Final[str] = "https://bcourses.berkeley.edu"

DEFAULT_TIMEZONE: Final[str] = "America/Los_Angeles"
DEFAULT_CAPACITY_HOURS_PER_DAY: Final[float] = 2.0

_ENV_HOME: Final[str] = "OPENMIND_HOME"


class ConfigError(Exception):
    """Raised when the configuration is missing or unusable."""


def home_dir() -> Path:
    """Return the OpenMind MCP home directory (``~/.openmind/mcp`` by default)."""
    override = os.environ.get(_ENV_HOME, "").strip()
    if override:
        return Path(override).expanduser()
    return Path.home() / ".openmind" / "mcp"


def config_path() -> Path:
    """Return the path of the config file."""
    return home_dir() / "config.json"


def index_db_path() -> Path:
    """Return the path of the opt-in course materials index."""
    return home_dir() / "index.db"


def catalog_db_path() -> Path:
    """Return the path of the public Berkeley catalog index."""
    return home_dir() / "catalog.db"


def validate_canvas_url(url: str) -> bool:
    """Check that a Canvas URL points to a trusted Berkeley host over HTTPS."""
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return host in ALLOWED_CANVAS_HOSTS


class Config:
    """The student's non-secret settings."""

    __slots__ = ("_raw", "path")

    def __init__(self, raw: Mapping[str, Any] | None = None, path: Path | None = None) -> None:
        self._raw: dict[str, Any] = dict(raw or {})
        self.path: Path = path or config_path()

    # -- accessors ---------------------------------------------------------

    @property
    def canvas_url(self) -> str:
        """Return the fixed bCourses base URL."""
        url = str(self._raw.get("canvas_url") or CANVAS_URL).rstrip("/")
        if not validate_canvas_url(url):
            raise ConfigError(f"Canvas URL {url!r} is not a permitted Berkeley host.")
        return url

    @property
    def time_zone(self) -> str:
        """Return the student's IANA time zone, as reported by their Canvas profile."""
        return str(self._raw.get("time_zone") or DEFAULT_TIMEZONE)

    @property
    def user_name(self) -> str:
        """Return the student's display name from their Canvas profile."""
        return str(self._raw.get("user_name") or "")

    @property
    def courses(self) -> dict[str, str]:
        """Return enabled ``{course_id: nickname}`` pairs."""
        raw = self._raw.get("courses")
        if not isinstance(raw, dict):
            return {}
        return {str(k): str(v) for k, v in raw.items()}

    @property
    def enabled_course_ids(self) -> tuple[str, ...]:
        """Return the ids of the courses the student chose to share."""
        return tuple(self.courses)

    @property
    def indexed_course_ids(self) -> tuple[str, ...]:
        """Return the ids of courses with a local materials index enabled."""
        raw = self._raw.get("index_enabled")
        if not isinstance(raw, list):
            return ()
        return tuple(str(cid) for cid in raw if str(cid) in self.courses)

    @property
    def capacity_hours_per_day(self) -> float:
        """Return the study hours per day assumed when computing start-by dates."""
        try:
            value = float(self._raw.get("capacity_hours_per_day", DEFAULT_CAPACITY_HOURS_PER_DAY))
        except (TypeError, ValueError):
            return DEFAULT_CAPACITY_HOURS_PER_DAY
        return value if 0.5 <= value <= 16.0 else DEFAULT_CAPACITY_HOURS_PER_DAY

    @property
    def data_updates(self) -> bool:
        """Return whether the client may check GitHub for newer public catalog data."""
        return bool(self._raw.get("data_updates", True))

    @property
    def allow_file_secrets(self) -> bool:
        """Return whether the Canvas token may fall back to a 0600 file."""
        return bool(self._raw.get("allow_file_secrets", False))

    def is_enabled(self, course_id: str) -> bool:
        """Return whether a course id was enabled by the student."""
        return str(course_id) in self.courses

    def nickname(self, course_id: str) -> str:
        """Return the student's nickname for a course, or the id when unknown."""
        return self.courses.get(str(course_id), str(course_id))

    def require_enabled(self, course_id: str) -> str:
        """Return a validated, enabled course id or raise :class:`ConfigError`."""
        cid = str(course_id).strip()
        if not self.is_enabled(cid):
            known = ", ".join(sorted(self.courses)) or "none"
            raise ConfigError(
                f"Course {cid} is not one of your enabled courses (enabled: {known}). "
                "Call list_courses first, or run `openmind setup` to change which courses you share."
            )
        return cid

    # -- mutation ----------------------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """Set a raw config value."""
        self._raw[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Return a raw config value."""
        return self._raw.get(key, default)

    def as_dict(self) -> dict[str, Any]:
        """Return a copy of the raw config mapping."""
        return dict(self._raw)

    def save(self) -> None:
        """Write the config to disk atomically with owner-only permissions."""
        save_config(self._raw, self.path)


def load_config(*, required: bool = False) -> Config:
    """Load the config from disk.

    With ``required=True`` a missing or empty config raises :class:`ConfigError` naming
    the setup command, which is what every tool call needs.
    """
    path = config_path()
    raw: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ConfigError(f"Could not read {path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ConfigError(f"{path} must contain a JSON object.")
        raw = data

    cfg = Config(raw, path)
    if required and not cfg.courses:
        raise ConfigError("OpenMind is not set up yet. Run `openmind setup` in a terminal, then restart your AI app.")
    return cfg


def save_config(cfg: Mapping[str, Any], path: Path | None = None) -> None:
    """Write config to disk atomically with restricted permissions."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(target.parent, stat.S_IRWXU)
    except OSError:  # pragma: no cover - Windows and exotic filesystems
        logger.debug("Could not restrict permissions on %s", target.parent)

    content = json.dumps(dict(cfg), indent=2, sort_keys=True)
    fd, tmp_path = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        tmp = Path(tmp_path)
        try:
            tmp.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:  # pragma: no cover
            logger.debug("Could not restrict permissions on %s", tmp)
        tmp.replace(target)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise
