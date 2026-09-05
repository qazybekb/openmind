"""Find and edit the config files AI apps read at launch.

Every supported host stores the same thing — a command to run — in a slightly different
place and format. Editing those files by hand is where students get stuck: a missing
comma, a relative path, or an edit to the wrong file all fail silently, and the host
reports nothing more useful than "no such tool".

Two rules govern every write here. Nothing but the absolute path of ``openmind-mcp``
ever goes into the entry, and nothing outside the ``openmind`` entry is touched — a
student's other MCP servers are none of our business, so the file is merged rather than
replaced, and backed up first.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final

ENTRY_NAME: Final[str] = "openmind"
ENV_OVERRIDE: Final[str] = "OPENMIND_HOST_CONFIG_DIR"


class HostError(Exception):
    """A host config could not be read or written."""


@dataclass(frozen=True)
class Host:
    """One AI app: where its config lives and how its entries are shaped."""

    key: str
    label: str
    path: Path | None
    container: str | None
    note: str = ""

    @property
    def writable(self) -> bool:
        """Return whether this host has a config file OpenMind can edit."""
        return self.path is not None


def server_command() -> tuple[str, list[str]]:
    """Return the command and arguments that launch the MCP server.

    Prefers the installed ``openmind-mcp`` console script, because a host does not
    inherit the shell's PATH and needs an absolute path it can execute directly.
    """
    found = shutil.which("openmind-mcp")
    if found:
        return str(Path(found).resolve()), []
    return str(Path(sys.executable).resolve()), ["-m", "openmind.server"]


def entry() -> dict[str, Any]:
    """Return the config entry for OpenMind. No secrets, ever — only a path."""
    command, args = server_command()
    return {"command": command, **({"args": args} if args else {})}


def command_line() -> str:
    """Return the launch command as a shell would spell it."""
    command, args = server_command()
    return " ".join([command, *args])


def _override_dir() -> Path | None:
    """Return the test override for host config locations, when set.

    Writing to a student's real Claude config from a test suite would be unforgivable,
    so the paths are redirectable and the tests always redirect them.
    """
    raw = os.environ.get(ENV_OVERRIDE, "").strip()
    return Path(raw).expanduser() if raw else None


def claude_desktop_path() -> Path:
    """Return the Claude Desktop config path for this platform."""
    override = _override_dir()
    if override is not None:
        return override / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def cursor_path() -> Path:
    """Return the Cursor MCP config path."""
    override = _override_dir()
    if override is not None:
        return override / "cursor_mcp.json"
    return Path.home() / ".cursor" / "mcp.json"


def hosts() -> list[Host]:
    """Return every supported host, in the order the CLI presents them."""
    return [
        Host("claude-desktop", "Claude Desktop", claude_desktop_path(), "mcpServers"),
        Host("claude-code", "Claude Code", None, None,
             note=f"claude mcp add --scope user {ENTRY_NAME} -- {command_line()}"),
        Host("cursor", "Cursor", cursor_path(), "mcpServers"),
        Host("chatgpt", "ChatGPT desktop", None, None,
             note="Add a local (STDIO) MCP server in the app's settings with the command above."),
    ]


def find(key: str) -> Host:
    """Return one host by its CLI key."""
    for host in hosts():
        if host.key == key:
            return host
    known = ", ".join(host.key for host in hosts())
    raise HostError(f"Unknown host {key!r}. Choose one of: {known}.")


def read_config(path: Path) -> dict[str, Any]:
    """Read a host config, or an empty document when it does not exist yet."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HostError(
            f"{path} is not valid JSON ({exc}). Fix or move it, then run this again — "
            "OpenMind will not overwrite a file it cannot parse."
        ) from exc
    if not isinstance(data, dict):
        raise HostError(f"{path} does not contain a JSON object.")
    return data


def back_up(path: Path) -> Path:
    """Copy a config next to itself with a timestamp, and return the copy's path."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.{stamp}.bak")
    shutil.copy2(path, backup)
    return backup


def merge(host: Host, document: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Return the document with OpenMind's entry merged in, and a description of the change."""
    if host.container is None:  # pragma: no cover - guarded by the caller
        raise HostError(f"{host.label} has no config file to write.")

    merged = json.loads(json.dumps(document))
    servers = merged.setdefault(host.container, {})
    if not isinstance(servers, dict):
        raise HostError(f"{host.container!r} in this config is not an object; refusing to replace it.")

    wanted = entry()
    previous = servers.get(ENTRY_NAME)
    servers[ENTRY_NAME] = wanted

    if previous == wanted:
        change = "unchanged"
    elif previous is None:
        change = "added"
    else:
        change = "updated"
    return merged, change


def diff(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Return a unified diff of two config documents, for the student to read."""
    import difflib

    return list(
        difflib.unified_diff(
            json.dumps(before, indent=2, sort_keys=True).splitlines(),
            json.dumps(after, indent=2, sort_keys=True).splitlines(),
            fromfile="before",
            tofile="after",
            lineterm="",
            n=2,
        )
    )


def write_config(path: Path, document: dict[str, Any]) -> None:
    """Write a host config, creating its directory if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


@dataclass
class Status:
    """What a host's config currently says about OpenMind, for `openmind doctor`."""

    host: Host
    exists: bool
    configured: bool
    command: str | None
    runnable: bool
    current: bool

    def describe(self) -> str:
        """Return one line summarising this host's state."""
        if not self.exists:
            return f"{self.host.label}: no config file at {self.host.path}"
        if not self.configured:
            return f"{self.host.label}: config exists but has no openmind entry — run `openmind mcp --write {self.host.key}`"
        if not self.runnable:
            return f"{self.host.label}: entry points at {self.command}, which is missing or not executable"
        if not self.current:
            return (
                f"{self.host.label}: entry points at {self.command}, but this install is "
                f"{command_line()} — run `openmind mcp --write {self.host.key}` to update it"
            )
        return f"{self.host.label}: configured and current"

    @property
    def healthy(self) -> bool:
        """Return whether this host needs no attention."""
        return not self.exists or (self.configured and self.runnable and self.current)


def status(host: Host) -> Status | None:
    """Inspect one host's config. Returns ``None`` for hosts without a config file."""
    if host.path is None or host.container is None:
        return None

    exists = host.path.exists()
    configured = False
    command: str | None = None
    runnable = False
    current = False

    if exists:
        try:
            document = read_config(host.path)
        except HostError:
            return Status(host, exists=True, configured=False, command=None, runnable=False, current=False)
        found = (document.get(host.container) or {}).get(ENTRY_NAME)
        if isinstance(found, dict):
            configured = True
            command = " ".join([str(found.get("command") or ""), *(str(a) for a in found.get("args") or [])]).strip()
            executable = Path(str(found.get("command") or ""))
            runnable = executable.exists() and os.access(executable, os.X_OK)
            current = command == command_line()

    return Status(host, exists=exists, configured=configured, command=command, runnable=runnable, current=current)
