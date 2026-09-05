"""Keep an opt-in, per-course full-text index of course materials.

A student who has not enabled a course has nothing about that course on disk. When they
do enable one, the extracted text of its slides, readings, and pages lands in a 0600
SQLite file so the host can search *inside* documents instead of guessing from titles.
``openmind clear`` deletes the whole thing.

Search is FTS5 with bm25 ranking. Every query token is quoted before it reaches MATCH so
a document (or a model) cannot smuggle FTS operators into the query, and an AND search
falls back to OR and then to LIKE so a precise phrase never returns a bare "no results".
"""

from __future__ import annotations

import logging
import re
import sqlite3
import stat
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from openmind.config import index_db_path
from openmind.materials import Chunk, cite

logger = logging.getLogger(__name__)

SCHEMA_VERSION: Final[str] = "1"
MAX_COURSE_CHARS: Final[int] = 20 * 1024 * 1024
SNIPPET_CHARS: Final[int] = 320
MAX_CHUNKS_PER_MATERIAL: Final[int] = 2

KINDS: Final[tuple[str, ...]] = ("syllabus", "page", "file", "announcement", "assignment")

_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('syllabus','page','file','announcement','assignment')),
    canvas_id TEXT NOT NULL,
    title TEXT NOT NULL,
    module_name TEXT,
    module_position INTEGER,
    item_position INTEGER,
    html_url TEXT,
    content_type TEXT,
    size_bytes INTEGER,
    page_count INTEGER,
    source_updated_at TEXT,
    content_sha1 TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','indexed','skipped','failed','deleted')),
    status_note TEXT,
    char_count INTEGER DEFAULT 0,
    truncated INTEGER DEFAULT 0,
    indexed_at TEXT,
    UNIQUE (course_id, kind, canvas_id)
);
CREATE INDEX IF NOT EXISTS materials_course ON materials (course_id, status);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES materials (id) ON DELETE CASCADE,
    ord INTEGER NOT NULL,
    page_start INTEGER,
    page_end INTEGER,
    heading TEXT,
    title TEXT,
    text TEXT NOT NULL,
    char_count INTEGER,
    UNIQUE (material_id, ord)
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5 (
    text, heading, title,
    content='chunks', content_rowid='id',
    tokenize='porter unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts (rowid, text, heading, title)
    VALUES (new.id, new.text, new.heading, new.title);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text, heading, title)
    VALUES ('delete', old.id, old.text, old.heading, old.title);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text, heading, title)
    VALUES ('delete', old.id, old.text, old.heading, old.title);
    INSERT INTO chunks_fts (rowid, text, heading, title)
    VALUES (new.id, new.text, new.heading, new.title);
END;
"""


class IndexError_(Exception):
    """The materials index could not be opened or written."""


@dataclass
class Hit:
    """One search result, ready to quote."""

    material_id: int
    canvas_id: str
    kind: str
    title: str
    module_name: str | None
    page_start: int
    page_end: int
    heading: str | None
    snippet: str
    html_url: str | None

    def to_dict(self) -> dict[str, Any]:
        """Render for a tool payload."""
        paged = self.kind == "file"
        payload = {
            "material_id": self.material_id,
            "kind": self.kind,
            "title": self.title,
            "excerpt": self.snippet,
            "cite": cite(self.title, self.page_start, self.page_end, self.heading, paged=paged),
        }
        if self.module_name:
            payload["module"] = self.module_name
        if self.html_url:
            payload["url"] = self.html_url
        return payload


def fts5_available(connection: sqlite3.Connection | None = None) -> bool:
    """Return whether this Python's SQLite was built with FTS5."""
    own = connection is None
    conn = connection or sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE _probe USING fts5(x)")
        conn.execute("DROP TABLE _probe")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        if own:
            conn.close()


@contextmanager
def connect(path: Path | None = None, *, create: bool = True) -> Iterator[sqlite3.Connection]:
    """Open the index database for one operation and close it afterwards."""
    target = path or index_db_path()
    if not create and not target.exists():
        raise IndexError_("No course materials are indexed yet. Run `openmind index --course <id>` first.")
    target.parent.mkdir(parents=True, exist_ok=True)
    fresh = not target.exists()
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        if create:
            connection.executescript(_SCHEMA)
            connection.execute(
                "INSERT INTO meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (SCHEMA_VERSION,),
            )
            connection.commit()
        if fresh:
            try:
                target.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:  # pragma: no cover - Windows
                logger.debug("Could not restrict permissions on the index database.")
        yield connection
    finally:
        connection.close()


# -- writes -------------------------------------------------------------------


def upsert_material(conn: sqlite3.Connection, *, course_id: str, kind: str, canvas_id: str, title: str,
                    module_name: str | None = None, module_position: int | None = None,
                    item_position: int | None = None, html_url: str | None = None,
                    content_type: str | None = None, size_bytes: int | None = None,
                    source_updated_at: str | None = None) -> int:
    """Record that a material exists, leaving it ``pending`` until its text is extracted."""
    conn.execute(
        """
        INSERT INTO materials (course_id, kind, canvas_id, title, module_name, module_position,
                               item_position, html_url, content_type, size_bytes, source_updated_at, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        ON CONFLICT (course_id, kind, canvas_id) DO UPDATE SET
            title = excluded.title,
            module_name = COALESCE(excluded.module_name, materials.module_name),
            module_position = COALESCE(excluded.module_position, materials.module_position),
            item_position = COALESCE(excluded.item_position, materials.item_position),
            html_url = COALESCE(excluded.html_url, materials.html_url),
            content_type = COALESCE(excluded.content_type, materials.content_type),
            size_bytes = COALESCE(excluded.size_bytes, materials.size_bytes),
            status = CASE
                WHEN materials.source_updated_at IS NOT excluded.source_updated_at THEN 'pending'
                ELSE materials.status END,
            source_updated_at = excluded.source_updated_at
        """,
        (course_id, kind, canvas_id, title, module_name, module_position, item_position,
         html_url, content_type, size_bytes, source_updated_at),
    )
    row = conn.execute(
        "SELECT id FROM materials WHERE course_id = ? AND kind = ? AND canvas_id = ?",
        (course_id, kind, canvas_id),
    ).fetchone()
    return int(row["id"])


def store_chunks(conn: sqlite3.Connection, material_id: int, title: str, chunks: Iterable[Chunk], *,
                 page_count: int = 0, truncated: bool = False) -> int:
    """Replace a material's chunks and mark it indexed."""
    conn.execute("DELETE FROM chunks WHERE material_id = ?", (material_id,))
    total = 0
    for chunk in chunks:
        text = chunk.text.strip()
        if not text:
            continue
        conn.execute(
            "INSERT INTO chunks (material_id, ord, page_start, page_end, heading, title, text, char_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (material_id, chunk.ord, chunk.page_start, chunk.page_end, chunk.heading, title, text, len(text)),
        )
        total += len(text)
    conn.execute(
        "UPDATE materials SET status = 'indexed', status_note = NULL, char_count = ?, page_count = ?, "
        "truncated = ?, indexed_at = ? WHERE id = ?",
        (total, page_count, 1 if truncated else 0, datetime.now(UTC).isoformat(), material_id),
    )
    conn.commit()
    return total


def mark(conn: sqlite3.Connection, material_id: int, status: str, note: str | None = None) -> None:
    """Record why a material was skipped or failed, so the student is told rather than left guessing."""
    conn.execute(
        "UPDATE materials SET status = ?, status_note = ?, indexed_at = ? WHERE id = ?",
        (status, note, datetime.now(UTC).isoformat(), material_id),
    )
    conn.commit()


def pending(conn: sqlite3.Connection, course_id: str, limit: int = 50) -> list[sqlite3.Row]:
    """Return materials waiting to be extracted, biggest-value first."""
    return list(
        conn.execute(
            "SELECT * FROM materials WHERE course_id = ? AND status = 'pending' "
            "ORDER BY module_position IS NULL, module_position, item_position, id LIMIT ?",
            (course_id, limit),
        )
    )


def course_stats(conn: sqlite3.Connection, course_id: str) -> dict[str, int]:
    """Summarise how much of a course is indexed."""
    rows = conn.execute(
        "SELECT status, COUNT(*) AS n, COALESCE(SUM(char_count), 0) AS chars "
        "FROM materials WHERE course_id = ? GROUP BY status",
        (course_id,),
    ).fetchall()
    stats = {"indexed": 0, "pending": 0, "skipped": 0, "failed": 0, "chars": 0}
    for row in rows:
        stats[str(row["status"])] = int(row["n"])
        stats["chars"] += int(row["chars"])
    return stats


def indexed_courses(conn: sqlite3.Connection) -> list[str]:
    """Return course ids that have at least one indexed material."""
    return [str(row["course_id"]) for row in conn.execute(
        "SELECT DISTINCT course_id FROM materials WHERE status = 'indexed' ORDER BY course_id"
    )]


def clear_course(conn: sqlite3.Connection, course_id: str) -> int:
    """Delete everything stored for one course."""
    count = int(conn.execute("SELECT COUNT(*) FROM materials WHERE course_id = ?", (course_id,)).fetchone()[0])
    conn.execute("DELETE FROM chunks WHERE material_id IN (SELECT id FROM materials WHERE course_id = ?)", (course_id,))
    conn.execute("DELETE FROM materials WHERE course_id = ?", (course_id,))
    conn.commit()
    return count


def clear_all(path: Path | None = None) -> bool:
    """Delete the whole index file. Returns whether anything was removed."""
    target = path or index_db_path()
    removed = False
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(target) + suffix)
        if candidate.exists():
            candidate.unlink()
            removed = True
    return removed


# -- search -------------------------------------------------------------------

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'&.-]*")


def build_match(query: str, *, join: str = "AND") -> str:
    """Build a safe FTS5 MATCH expression.

    Each token is wrapped in double quotes, which makes it a literal string in FTS5
    syntax. That is what stops ``NEAR``, ``*``, ``OR``, or a stray quote in a document
    title from being read as query syntax.
    """
    tokens = [token.replace('"', "") for token in _TOKEN.findall(query or "")]
    tokens = [token for token in tokens if token]
    if not tokens:
        return ""
    return f" {join} ".join(f'"{token}"' for token in tokens[:12])


def search(conn: sqlite3.Connection, course_id: str, query: str, *, limit: int = 10,
           kind: str | None = None, offset: int = 0) -> list[Hit]:
    """Search a course's indexed materials, widening the query until something matches."""
    for join in ("AND", "OR"):
        expression = build_match(query, join=join)
        if not expression:
            break
        hits = _match(conn, course_id, expression, limit=limit, kind=kind, offset=offset)
        if hits:
            return hits
    return _like(conn, course_id, query, limit=limit, kind=kind, offset=offset)


def _match(conn: sqlite3.Connection, course_id: str, expression: str, *, limit: int, kind: str | None,
           offset: int) -> list[Hit]:
    """Run a bm25-ranked FTS query, keeping at most two chunks per material."""
    sql = f"""
        SELECT m.id AS material_id, m.canvas_id, m.kind, m.title, m.module_name, m.html_url,
               c.page_start, c.page_end, c.heading,
               snippet(chunks_fts, 0, '[', ']', ' … ', 24) AS snippet,
               bm25(chunks_fts, 8.0, 4.0, 2.0) AS rank
        FROM chunks_fts
        JOIN chunks c ON c.id = chunks_fts.rowid
        JOIN materials m ON m.id = c.material_id
        WHERE chunks_fts MATCH ? AND m.course_id = ? AND m.status = 'indexed'
              {"AND m.kind = ?" if kind else ""}
        ORDER BY rank
        LIMIT ? OFFSET ?
    """
    params: list[Any] = [expression, course_id]
    if kind:
        params.append(kind)
    params.extend([limit * MAX_CHUNKS_PER_MATERIAL * 2, offset])
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        logger.debug("FTS query failed for %r", expression[:60])
        return []
    return _collect(rows, limit)


def _like(conn: sqlite3.Connection, course_id: str, query: str, *, limit: int, kind: str | None,
          offset: int) -> list[Hit]:
    """Fall back to a substring scan when the tokenizer finds nothing."""
    needle = (query or "").strip()
    if not needle:
        return []
    sql = f"""
        SELECT m.id AS material_id, m.canvas_id, m.kind, m.title, m.module_name, m.html_url,
               c.page_start, c.page_end, c.heading, substr(c.text, 1, ?) AS snippet
        FROM chunks c
        JOIN materials m ON m.id = c.material_id
        WHERE m.course_id = ? AND m.status = 'indexed'
              AND (c.text LIKE ? ESCAPE '\\' OR m.title LIKE ? ESCAPE '\\')
              {"AND m.kind = ?" if kind else ""}
        ORDER BY m.module_position IS NULL, m.module_position, m.item_position, c.ord
        LIMIT ? OFFSET ?
    """
    pattern = "%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    params: list[Any] = [SNIPPET_CHARS, course_id, pattern, pattern]
    if kind:
        params.append(kind)
    params.extend([limit * MAX_CHUNKS_PER_MATERIAL, offset])
    rows = conn.execute(sql, params).fetchall()
    return _collect(rows, limit)


def _collect(rows: list[sqlite3.Row], limit: int) -> list[Hit]:
    """Turn result rows into hits, capping how many come from one document."""
    seen: dict[int, int] = {}
    hits: list[Hit] = []
    for row in rows:
        material_id = int(row["material_id"])
        if seen.get(material_id, 0) >= MAX_CHUNKS_PER_MATERIAL:
            continue
        seen[material_id] = seen.get(material_id, 0) + 1
        snippet = " ".join(str(row["snippet"] or "").split())[:SNIPPET_CHARS]
        hits.append(
            Hit(
                material_id=material_id,
                canvas_id=str(row["canvas_id"]),
                kind=str(row["kind"]),
                title=str(row["title"]),
                module_name=row["module_name"],
                page_start=int(row["page_start"] or 0),
                page_end=int(row["page_end"] or 0),
                heading=row["heading"],
                snippet=snippet,
                html_url=row["html_url"],
            )
        )
        if len(hits) >= limit:
            break
    return hits


def list_materials(conn: sqlite3.Connection, course_id: str, *, kind: str | None = None, limit: int = 25,
                   offset: int = 0) -> list[dict[str, Any]]:
    """List a course's known materials in module order."""
    sql = f"""
        SELECT id, canvas_id, kind, title, module_name, status, status_note, page_count, html_url
        FROM materials
        WHERE course_id = ? AND status != 'deleted' {"AND kind = ?" if kind else ""}
        ORDER BY module_position IS NULL, module_position, item_position, id
        LIMIT ? OFFSET ?
    """
    params: list[Any] = [course_id]
    if kind:
        params.append(kind)
    params.extend([limit, offset])
    results = []
    for row in conn.execute(sql, params):
        entry = {
            "material_id": int(row["id"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "status": str(row["status"]),
        }
        if row["module_name"]:
            entry["module"] = str(row["module_name"])
        if row["status_note"]:
            entry["note"] = str(row["status_note"])
        if row["page_count"]:
            entry["pages"] = int(row["page_count"])
        if row["html_url"]:
            entry["url"] = str(row["html_url"])
        results.append(entry)
    return results


def get_material(conn: sqlite3.Connection, material_id: int) -> sqlite3.Row | None:
    """Return one material record by its local id."""
    return conn.execute("SELECT * FROM materials WHERE id = ?", (int(material_id),)).fetchone()


def material_text(conn: sqlite3.Connection, material_id: int, page: int | None = None) -> list[sqlite3.Row]:
    """Return a material's chunks, optionally limited to one page."""
    if page is not None:
        return list(
            conn.execute(
                "SELECT * FROM chunks WHERE material_id = ? AND page_start <= ? AND page_end >= ? ORDER BY ord",
                (int(material_id), int(page), int(page)),
            )
        )
    return list(conn.execute("SELECT * FROM chunks WHERE material_id = ? ORDER BY ord", (int(material_id),)))
