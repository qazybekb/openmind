"""Session memory — persist conversation context across sessions."""

from __future__ import annotations

import json
import logging
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

from openmind.config import CONFIG_DIR

logger = logging.getLogger(__name__)

MEMORY_FILE: Final[Path] = CONFIG_DIR / "memory.json"
MAX_MEMORY_ENTRIES: Final[int] = 50
MAX_CONVERSATION_SUMMARY_CHARS: Final[int] = 2000


def _ensure_private_dir() -> None:
    """Create config directory with owner-only permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, stat.S_IRWXU)


def load_memory() -> list[dict[str, Any]]:
    """Load conversation memory entries."""
    if not MEMORY_FILE.exists():
        return []

    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to load memory", exc_info=True)

    return []


def save_memory(entries: list[dict[str, Any]]) -> None:
    """Persist memory entries atomically."""
    _ensure_private_dir()
    tmp_path: str | None = None
    try:
        fd, tmp_path = tempfile.mkstemp(dir=CONFIG_DIR, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(entries[-MAX_MEMORY_ENTRIES:], handle, indent=2, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_file = Path(tmp_path)
        tmp_file.chmod(stat.S_IRUSR | stat.S_IWUSR)
        tmp_file.replace(MEMORY_FILE)
    except OSError:
        logger.warning("Failed to save memory", exc_info=True)
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


def consolidate_conversation(messages: list[dict[str, Any]]) -> None:
    """Summarize the current conversation and save to memory.

    Extracts key topics, questions asked, and facts learned — not a full
    transcript. This gives future sessions context without bloating the prompt.
    """
    if len(messages) < 4:
        return

    # Extract user messages and assistant responses
    topics: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        content = str(msg.get("content", ""))
        if role == "user" and content:
            topics.append(f"Q: {content[:200]}")
        elif role == "assistant" and content and len(content) > 50:
            topics.append(f"A: {content[:200]}")

    if not topics:
        return

    summary = "\n".join(topics[:20])
    if len(summary) > MAX_CONVERSATION_SUMMARY_CHARS:
        summary = summary[:MAX_CONVERSATION_SUMMARY_CHARS] + "..."

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "message_count": len(messages),
    }

    entries = load_memory()
    entries.append(entry)
    save_memory(entries)


def format_memory_context() -> str:
    """Format recent memory entries for the system prompt."""
    entries = load_memory()
    if not entries:
        return ""

    recent = entries[-5:]
    lines = ["Previous conversation context:"]
    for entry in recent:
        ts = entry.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                ts = dt.strftime("%b %d, %H:%M")
            except ValueError:
                pass
        summary = entry.get("summary", "")
        # Only include user questions for brevity
        questions = [line for line in summary.split("\n") if line.startswith("Q: ")]
        if questions:
            lines.append(f"  [{ts}] {'; '.join(q[3:] for q in questions[:3])}")

    return "\n".join(lines) if len(lines) > 1 else ""
