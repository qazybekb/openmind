"""Read and write Obsidian notes with traversal-safe paths."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Final, TypeAlias

from openmind.config import ConfigDict

logger = logging.getLogger(__name__)

ToolArgs: TypeAlias = dict[str, Any]
ToolDefinition: TypeAlias = dict[str, Any]

MAX_SEARCH_MATCHES: Final[int] = 20

OBSIDIAN_TOOLS: list[ToolDefinition] = [
    {
        "type": "function",
        "function": {
            "name": "obsidian_read",
            "description": "Read a note from the Obsidian vault by path (e.g. 'Readings/Author Title.md').",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path within the vault"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_write",
            "description": "Write or update a note in the Obsidian vault. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path (e.g. 'Readings/Author Title.md')"},
                    "content": {"type": "string", "description": "Markdown content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "obsidian_search",
            "description": "Search for notes in the Obsidian vault by filename or content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search term"},
                },
                "required": ["query"],
            },
        },
    },
]


def _json_result(payload: Any) -> str:
    """Serialize an Obsidian tool payload as JSON."""
    return json.dumps(payload, default=str)


def _error_result(message: str) -> str:
    """Serialize an Obsidian tool error as JSON."""
    return _json_result({"error": message})


def _vault_path(cfg: ConfigDict) -> Path | None:
    """Resolve and validate the Obsidian vault path from config."""
    obsidian = cfg.get("obsidian", {})
    if not obsidian.get("enabled"):
        return None

    raw_path = str(obsidian.get("vault_path", "")).strip()
    if not raw_path:
        return None

    vault = Path(raw_path).expanduser().resolve()
    if not vault.is_absolute():
        return None

    if not vault.exists():
        try:
            vault.mkdir(parents=True, exist_ok=True)
        except OSError:
            logger.warning("Failed to create Obsidian vault at %s", vault, exc_info=True)
            return None

    return vault


def _is_within_vault(target: Path, vault: Path) -> bool:
    """Return whether a resolved path stays inside the configured vault."""
    return target.resolve().is_relative_to(vault.resolve())


def _resolve_target(vault: Path, relative_path: str) -> Path | None:
    """Resolve a relative path and reject traversal outside the vault."""
    if not relative_path.strip():
        return None

    target = (vault / relative_path).resolve()
    if not _is_within_vault(target, vault):
        return None
    return target


def execute_obsidian_tool(name: str, args: ToolArgs, cfg: ConfigDict) -> str:
    """Execute an Obsidian tool and return a JSON string."""
    vault = _vault_path(cfg)
    if vault is None:
        return _error_result("Obsidian not configured. Run: openmind setup")

    try:
        return _execute_obsidian_tool(name, args, vault)
    except Exception:
        logger.exception("Obsidian tool '%s' failed unexpectedly", name)
        return _error_result("Obsidian tool failed unexpectedly.")


def _execute_obsidian_tool(name: str, args: ToolArgs, vault: Path) -> str:
    """Dispatch an Obsidian tool after validating its arguments."""
    if name == "obsidian_read":
        relative_path = str(args.get("path", "")).strip()
        target = _resolve_target(vault, relative_path)
        if target is None:
            return _error_result("Invalid path.")
        if not target.exists() or not target.is_file():
            return _error_result(f"Note not found: {relative_path}")

        try:
            content = target.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Failed to read Obsidian note %s", target, exc_info=True)
            return _error_result("Failed to read the note.")
        return _json_result({"content": content})

    if name == "obsidian_write":
        relative_path = str(args.get("path", "")).strip()
        content = str(args.get("content", ""))
        target = _resolve_target(vault, relative_path)
        if target is None:
            return _error_result("Invalid path.")

        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError:
            logger.warning("Failed to write Obsidian note %s", target, exc_info=True)
            return _error_result("Failed to write the note.")
        return _json_result({"result": f"Saved to {relative_path}"})

    if name == "obsidian_search":
        query = str(args.get("query", "")).strip().lower()
        if not query:
            return _json_result({"matches": [], "count": 0})

        matches: list[str] = []
        for filepath in vault.rglob("*.md"):
            try:
                resolved_path = filepath.resolve()
            except OSError:
                continue

            if not _is_within_vault(resolved_path, vault):
                continue

            relative_name = str(filepath.relative_to(vault))
            if query in relative_name.lower():
                matches.append(relative_name)
            else:
                try:
                    text = resolved_path.read_text(encoding="utf-8", errors="replace").lower()
                except OSError:
                    continue
                if query in text:
                    matches.append(relative_name)

            if len(matches) >= MAX_SEARCH_MATCHES:
                break

        return _json_result({"matches": matches, "count": len(matches)})

    return _error_result(f"Unknown obsidian tool: {name}")
