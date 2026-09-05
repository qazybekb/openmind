"""Search the Berkeley course catalog and the terms courses are actually offered.

The catalog answers "does this course exist and what is it about"; the offerings table
answers "can I take it this semester", which is the question that actually matters when
a student is picking classes. Both are public data, both ship in the package so day one
works offline, and both carry the date they were captured — advice from a stale catalog
should look stale.

The refresh cadence is decoupled from releases: `scripts/refresh_catalog.py` runs in CI
and publishes a data asset, and the client checks for it at most once a day, verifies
the SHA-256, and rebuilds. That check is a public-file GET carrying nothing about the
student, and `data_updates: false` turns it off entirely.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import re
import sqlite3
import tarfile
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Final

from openmind.config import catalog_db_path, home_dir

logger = logging.getLogger(__name__)

MANIFEST_URL: Final[str] = (
    "https://raw.githubusercontent.com/qazybekb/openmind/main/src/openmind/data/catalog_meta.json"
)
ASSET_URL_TEMPLATE: Final[str] = "https://github.com/qazybekb/openmind/releases/download/data-{date}/catalog-{date}.tar.gz"
UPDATE_TIMEOUT_S: Final[float] = 20.0
UPDATE_INTERVAL_S: Final[float] = 24 * 3600
MAX_ASSET_BYTES: Final[int] = 32 * 1024 * 1024

MAX_LIMIT: Final[int] = 30
DEFAULT_LIMIT: Final[int] = 10
# Search results carry a gist; `get_catalog_course` returns the whole text. The gist
# is shortened further, down to MIN_PREVIEW, when a page of results would otherwise
# exceed the tool's byte budget — see `fit_previews`.
SEARCH_PREVIEW: Final[int] = 200
MIN_PREVIEW: Final[int] = 80
DESCRIPTION_PREVIEW: Final[int] = 300

MIN_COURSES: Final[int] = 10_000
MIN_SUBJECTS: Final[int] = 200
# Bumped when the built shape changes, so an index from an older version is rebuilt
# rather than queried with columns it does not have.
SCHEMA_VERSION: Final[str] = "2"
# How many rows to read per requested result before collapsing cross-listings. The
# floor is a guess; the real bound is the largest group in the data, recorded at build
# time — the packaged catalog has groups of 8, and a constant of 6 would leave a page
# short whenever such a group ranks consecutively.
_MIN_OVERFETCH: Final[int] = 6

_CSV_FILES: Final[dict[str, str]] = {
    "undergraduate_courses.csv": "undergraduate",
    "graduate_courses.csv": "graduate",
}

_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS catalog_courses (
    subject TEXT NOT NULL,
    number TEXT NOT NULL,
    level TEXT NOT NULL CHECK (level IN ('undergraduate','graduate')),
    title TEXT NOT NULL,
    units_min TEXT,
    units_max TEXT,
    department TEXT,
    description TEXT,
    cross_listed TEXT,
    repeat_rules TEXT,
    offering_details TEXT,
    in_printed_catalog INTEGER NOT NULL DEFAULT 1,
    group_key TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (subject, number)
);
CREATE INDEX IF NOT EXISTS catalog_group ON catalog_courses (group_key);

CREATE VIRTUAL TABLE IF NOT EXISTS catalog_fts USING fts5 (
    subject, number, title, description, content='catalog_courses'
);

CREATE TABLE IF NOT EXISTS term_offerings (
    subject TEXT NOT NULL,
    number TEXT NOT NULL,
    term TEXT NOT NULL,
    section_count INTEGER DEFAULT 0,
    instruction_modes TEXT,
    instructors TEXT,
    PRIMARY KEY (subject, number, term)
);
CREATE INDEX IF NOT EXISTS offerings_term ON term_offerings (term);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


class CatalogError(Exception):
    """The catalog index is missing or could not be built."""


@contextmanager
def connect(path: Path | None = None, *, create: bool = False) -> Iterator[sqlite3.Connection]:
    """Open the catalog database for one operation."""
    target = path or catalog_db_path()
    if not create and not target.exists():
        raise CatalogError("The Berkeley course catalog is not built yet. Run `openmind setup` or `openmind update-data`.")
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    try:
        if create:
            connection.executescript(_SCHEMA)
            connection.commit()
        yield connection
    finally:
        connection.close()


# -- building -----------------------------------------------------------------


_CROSS_CODE = re.compile(r"^([A-Z]+)([A-Z]{0,2}[0-9][0-9A-Z]*)$")


def parse_cross_listed(value: str, subjects: set[str]) -> list[tuple[str, str]]:
    """Split a ``cross_listed`` cell into course codes.

    The catalog writes these as ``DATAC204 ETHICS OF DATA, HISTORYC254 ETHICS OF DATA``
    — subject and number run together, then an abbreviated title. There is no separator
    to split on, so the subject is found by matching the longest known subject that
    leaves a plausible course number behind: ``HISTARTC196W`` is HISTART C196W, not
    HISTARTC 196W.
    """
    found: list[tuple[str, str]] = []
    for part in (value or "").split(","):
        token = part.strip().split(" ", 1)[0].upper()
        match = _CROSS_CODE.match(token)
        if not match:
            continue
        for cut in range(len(token) - 1, 0, -1):
            subject, number = token[:cut], token[cut:]
            if subject in subjects and _CROSS_CODE.match(f"{subject}{number}") and re.match(
                r"^[A-Z]{0,2}[0-9][0-9A-Z]*$", number
            ):
                found.append((subject, number))
                break
    return found


def build_groups(rows: list[tuple[Any, ...]], subject_index: int = 0, number_index: int = 1,
                 cross_index: int = 8) -> dict[tuple[str, str], str]:
    """Return a canonical group key for every course, joining cross-listed codes.

    The data is asymmetric in places — one code names its partners, another does not —
    so edges are followed in both directions and the group key is the alphabetically
    first code in the connected set. That makes the choice stable across runs and
    independent of which member the search happened to match.
    """
    known_subjects = {str(row[subject_index]) for row in rows}
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(key: tuple[str, str]) -> tuple[str, str]:
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    def union(left: tuple[str, str], right: tuple[str, str]) -> None:
        a, b = find(left), find(right)
        if a != b:
            parent[max(a, b)] = min(a, b)

    present = {(str(row[subject_index]), str(row[number_index])) for row in rows}
    for row in rows:
        key = (str(row[subject_index]), str(row[number_index]))
        find(key)
        for partner in parse_cross_listed(str(row[cross_index] or ""), known_subjects):
            if partner in present:
                union(key, partner)

    return {key: " ".join(find(key)) for key in present}


def _clean(value: str | None) -> str:
    """Normalise a catalog cell, treating the catalog's ``-`` placeholder as empty."""
    text = (value or "").strip()
    return "" if text in {"-", "--", "N/A"} else text


def data_dir() -> Path | None:
    """Return the packaged data directory, when it can be resolved to a real path."""
    try:
        path = resources.files("openmind.data")
    except (ModuleNotFoundError, TypeError):  # pragma: no cover
        return None
    try:
        return Path(str(path))
    except TypeError:  # pragma: no cover - zipped installs
        return None


def _read_csv(name: str) -> list[dict[str, str]]:
    """Read one packaged catalog CSV."""
    try:
        text = resources.files("openmind.data").joinpath(name).read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        logger.warning("Catalog file %s is missing from the package.", name)
        return []
    return list(csv.DictReader(io.StringIO(text)))


def load_meta_file() -> dict[str, Any]:
    """Read ``catalog_meta.json`` from the package, when present."""
    try:
        text = resources.files("openmind.data").joinpath("catalog_meta.json").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def build(path: Path | None = None, *, source_dir: Path | None = None) -> dict[str, int]:
    """Build the catalog index from CSV data. Returns row counts."""
    target = path or catalog_db_path()
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(target) + suffix)
        if candidate.exists():
            candidate.unlink()

    meta = _load_source_meta(source_dir)
    rows: list[tuple[Any, ...]] = []
    seen: set[tuple[str, str]] = set()
    for filename, level in _CSV_FILES.items():
        records = _read_source_csv(filename, source_dir)
        for record in records:
            subject = _clean(record.get("Subject")).upper()
            number = _clean(record.get("Course Number"))
            if not subject or not number:
                continue
            key = (subject, number)
            if key in seen:
                continue
            seen.add(key)
            in_catalog = _clean(record.get("In Printed Catalog")) or "1"
            rows.append(
                (
                    subject,
                    number,
                    level,
                    _clean(record.get("Course Title")),
                    _clean(record.get("Credits - Units - Minimum Units")),
                    _clean(record.get("Credits - Units - Maximum Units")),
                    _clean(record.get("Department(s)")),
                    _clean(record.get("Course Description")),
                    _clean(record.get("Cross-Listed Course(s)")),
                    _clean(record.get("Repeat Rules")),
                    " ".join(
                        part for part in (
                            _clean(record.get("Offering Information")),
                            _clean(record.get("Additional Offering Information")),
                        ) if part
                    ),
                    0 if in_catalog in {"0", "false", "False"} else 1,
                )
            )

    groups = build_groups(rows)
    rows = [(*row, groups[(row[0], row[1])]) for row in rows]
    largest_group = max(Counter(groups.values()).values(), default=1)
    offerings = _read_offerings(source_dir)

    with connect(target, create=True) as conn:
        conn.execute("DELETE FROM catalog_courses")
        conn.execute("DELETE FROM term_offerings")
        conn.execute("DELETE FROM catalog_fts")
        conn.executemany(
            "INSERT INTO catalog_courses (subject, number, level, title, units_min, units_max, department, "
            "description, cross_listed, repeat_rules, offering_details, in_printed_catalog, group_key) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.executemany(
            "INSERT OR REPLACE INTO term_offerings (subject, number, term, section_count, instruction_modes, "
            "instructors) VALUES (?, ?, ?, ?, ?, ?)",
            offerings,
        )
        conn.execute("INSERT INTO catalog_fts (catalog_fts) VALUES ('rebuild')")
        terms = sorted({row[2] for row in offerings})
        for key, value in {
            "catalog_as_of": meta.get("catalog_as_of") or date.today().isoformat(),
            "offerings_as_of": meta.get("offerings_as_of") or ("" if not offerings else date.today().isoformat()),
            # Why the offerings are older than the catalog, when they are. Carried out of
            # the manifest so a student is told once rather than left to compare dates.
            "offerings_note": meta.get("offerings_note") or "",
            "terms_known": json.dumps(meta.get("terms_known") or terms),
            "data_sha256": meta.get("data_sha256") or "",
            "max_group_size": largest_group,
            "schema_version": SCHEMA_VERSION,
            "built_at": datetime.now(UTC).isoformat(),
        }.items():
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )
        conn.commit()

    return {"courses": len(rows), "offerings": len(offerings), "subjects": len({row[0] for row in rows})}


def _read_source_csv(filename: str, source_dir: Path | None) -> list[dict[str, str]]:
    """Read a catalog CSV from an override directory, falling back to the package."""
    if source_dir is not None:
        candidate = source_dir / filename
        if candidate.exists():
            return list(csv.DictReader(io.StringIO(candidate.read_text(encoding="utf-8"))))
        return []
    return _read_csv(filename)


def _read_offerings(source_dir: Path | None) -> list[tuple[Any, ...]]:
    """Read ``term_offerings.csv`` when the data snapshot includes one."""
    records: list[dict[str, str]] = []
    if source_dir is not None:
        candidate = source_dir / "term_offerings.csv"
        if candidate.exists():
            records = list(csv.DictReader(io.StringIO(candidate.read_text(encoding="utf-8"))))
    else:
        try:
            text = resources.files("openmind.data").joinpath("term_offerings.csv").read_text(encoding="utf-8")
            records = list(csv.DictReader(io.StringIO(text)))
        except (FileNotFoundError, ModuleNotFoundError):
            records = []

    rows: list[tuple[Any, ...]] = []
    for record in records:
        subject = _clean(record.get("subject")).upper()
        number = _clean(record.get("number"))
        term = _clean(record.get("term"))
        if not (subject and number and term):
            continue
        try:
            sections = int(_clean(record.get("section_count")) or 0)
        except ValueError:
            sections = 0
        rows.append((subject, number, term, sections, _clean(record.get("instruction_modes")),
                     _clean(record.get("instructors"))))
    return rows


def _load_source_meta(source_dir: Path | None) -> dict[str, Any]:
    """Read the data manifest from an override directory or the package."""
    if source_dir is not None:
        candidate = source_dir / "catalog_meta.json"
        if candidate.exists():
            try:
                payload = json.loads(candidate.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return {}
            return payload if isinstance(payload, dict) else {}
        return {}
    return load_meta_file()


def ensure_built(path: Path | None = None) -> dict[str, int] | None:
    """Build the catalog index from the packaged CSVs if it does not exist yet.

    The catalog is public data that ships in the wheel, so there is no reason to make a
    student run setup — or hand over a Canvas token — before they can search it. The
    first catalog question builds it; every later one finds it already there.

    Returns the row counts when it built something, or ``None`` when it was already
    there.
    """
    target = path or catalog_db_path()
    if target.exists() and _schema_current(target):
        return None
    reason = "first run" if not target.exists() else "the index predates the current shape"
    logger.info("Building the Berkeley catalog index from packaged data (%s).", reason)
    return build(target)


def _schema_current(target: Path) -> bool:
    """Return whether an existing index was built by this version of the code."""
    try:
        with connect(target) as conn:
            return meta(conn).get("schema_version") == SCHEMA_VERSION
    except (CatalogError, sqlite3.DatabaseError):
        return False


# -- reads --------------------------------------------------------------------


def meta(conn: sqlite3.Connection) -> dict[str, str]:
    """Return the catalog's provenance fields."""
    return {str(row["key"]): str(row["value"]) for row in conn.execute("SELECT key, value FROM meta")}


def offerings_note(conn: sqlite3.Connection) -> str:
    """Return the snapshot's own note about its offerings, or "" when there is none.

    A refresh that could not reach the class schedule keeps the previous offerings and
    records why. Repeating that line wherever ``offerings_as_of`` is reported is what
    stops a stale date from being read as "this course is not offered".
    """
    return meta(conn).get("offerings_note", "").strip()


def terms_known(conn: sqlite3.Connection) -> list[str]:
    """Return the terms the offerings table covers, newest last."""
    raw = meta(conn).get("terms_known", "")
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        parsed = []
    if parsed:
        return [str(term) for term in parsed]
    return [str(row["term"]) for row in conn.execute("SELECT DISTINCT term FROM term_offerings ORDER BY term")]


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9&'-]*")


def _title_rank_patterns(query: str) -> tuple[str, str]:
    """Return the (exact, contains) lower-cased patterns used to rank titles."""
    wanted = " ".join((query or "").lower().split())
    escaped = wanted.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    return wanted, f"%{escaped}%"


def overfetch(conn: sqlite3.Connection) -> int:
    """Return how many rows to read per requested result before collapsing.

    Sized from the largest cross-listing group the data actually contains, so a page
    cannot come up short because eight codes for one course happened to rank together.
    """
    try:
        recorded = int(meta(conn).get("max_group_size") or 0)
    except (ValueError, TypeError):  # pragma: no cover - a hand-edited meta table
        recorded = 0
    return max(recorded, _MIN_OVERFETCH)


def _match_expression(query: str, join: str = "AND") -> str:
    """Quote every token so catalog text can never inject FTS operators."""
    tokens = [token.replace('"', "") for token in _TOKEN.findall(query or "")]
    return f" {join} ".join(f'"{token}"' for token in tokens[:12] if token)


def search(conn: sqlite3.Connection, *, query: str = "", subject: str | None = None, level: str | None = None,
           units: str | None = None, offered_term: str | None = None, limit: int = DEFAULT_LIMIT) -> dict[str, Any]:
    """Search the catalog, optionally restricted to courses offered in a term."""
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    clauses: list[str] = []
    params: list[Any] = []

    if subject:
        clauses.append("c.subject = ?")
        params.append(subject.strip().upper())
    if level:
        clauses.append("c.level = ?")
        params.append(level)
    if units:
        clauses.append("(c.units_min = ? OR c.units_max = ?)")
        params.extend([str(units).strip(), str(units).strip()])
    if offered_term:
        clauses.append("EXISTS (SELECT 1 FROM term_offerings o WHERE o.subject = c.subject "
                       "AND o.number = c.number AND o.term = ?)")
        params.append(offered_term)

    rows: list[sqlite3.Row] = []
    total = 0
    if query.strip():
        # "STAT 156" is a course code, not two search terms. Try it as one before
        # falling back to text search, which would otherwise rank every course
        # numbered 156 above the one the student named.
        code = parse_course_code(query)
        if code:
            where = " AND ".join(["c.subject = ?", "c.number = ?", *clauses])
            rows = conn.execute(
                f"SELECT c.* FROM catalog_courses c WHERE {where}", [code[0], code[1], *params]
            ).fetchall()
            total = len(rows)
        if rows:
            return _result(conn, rows, total, limit, subject)
        for join in ("AND", "OR"):
            expression = _match_expression(query, join)
            if not expression:
                break
            where = " AND ".join(["catalog_fts MATCH ?", *clauses])
            # bm25 alone buries the obvious answer: a course *called* "Causal
            # Inference" scores below one whose description happens to repeat the
            # words. Title equality comes first, then the phrase appearing in a title,
            # then relevance. The MATCH expression is still the quoted-token one, so
            # nothing here reopens operator injection.
            # Three tiers, then relevance. Inside tier 0 every title *is* the query, so
            # bm25 is noise there and would reorder identically-titled courses run to
            # run; the code decides instead, which is stable.
            sql = (
                "SELECT * FROM (SELECT c.*, bm25(catalog_fts, 4.0, 4.0, 8.0, 1.0) AS rank, "
                "  CASE WHEN lower(c.title) = ? THEN 0 "
                "       WHEN lower(c.title) LIKE ? ESCAPE '\\' THEN 1 "
                "       ELSE 2 END AS tier "
                "  FROM catalog_fts JOIN catalog_courses c ON c.rowid = catalog_fts.rowid "
                f"  WHERE {where}) "
                "ORDER BY tier, CASE WHEN tier = 0 THEN 0.0 ELSE rank END, subject, number LIMIT ?"
            )
            exact, phrase = _title_rank_patterns(query)
            try:
                rows = conn.execute(
                    sql, [exact, phrase, expression, *params, limit * overfetch(conn)]
                ).fetchall()
                total = int(conn.execute(
                    "SELECT COUNT(DISTINCT c.group_key) FROM catalog_fts "
                    f"JOIN catalog_courses c ON c.rowid = catalog_fts.rowid WHERE {where}",
                    [expression, *params],
                ).fetchone()[0])
            except sqlite3.OperationalError:
                rows, total = [], 0
            if rows:
                break
        if not rows:
            rows, total = _like_search(conn, query, clauses, params, limit)
    else:
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = conn.execute(
            f"SELECT c.* FROM catalog_courses c{where} ORDER BY c.subject, c.number LIMIT ?",
            [*params, limit * overfetch(conn)],
        ).fetchall()
        total = int(conn.execute(
            f"SELECT COUNT(DISTINCT c.group_key) FROM catalog_courses c{where}", params
        ).fetchone()[0])

    return _result(conn, rows, total, limit, subject)


def _like_search(conn: sqlite3.Connection, query: str, clauses: list[str], params: list[Any],
                 limit: int) -> tuple[list[sqlite3.Row], int]:
    """Fall back to a substring search, which is what makes ``STAT 156`` findable."""
    needle = "%" + query.strip().replace("%", r"\%").replace("_", r"\_") + "%"
    code = re.match(r"^\s*([A-Za-z][A-Za-z &]*?)\s*([0-9][0-9A-Za-z]*)\s*$", query or "")
    where = ["(c.title LIKE ? ESCAPE '\\' OR c.description LIKE ? ESCAPE '\\' OR (c.subject || ' ' || c.number) LIKE ? ESCAPE '\\')"]
    values: list[Any] = [needle, needle, needle]
    if code:
        where = ["((c.subject LIKE ? ESCAPE '\\' AND c.number = ?) OR " + where[0][1:-1] + ")"]
        values = [code.group(1).strip().upper() + "%", code.group(2).upper(), needle, needle, needle]
    full = " AND ".join([*where, *clauses])
    exact, phrase = _title_rank_patterns(query)
    rows = conn.execute(
        f"SELECT c.* FROM catalog_courses c WHERE {full} "
        "ORDER BY CASE WHEN lower(c.title) = ? THEN 0 "
        "              WHEN lower(c.title) LIKE ? ESCAPE '\\' THEN 1 "
        "              ELSE 2 END, c.subject, c.number LIMIT ?",
        [*values, *params, exact, phrase, limit * overfetch(conn)],
    ).fetchall()
    total = int(conn.execute(
        f"SELECT COUNT(DISTINCT c.group_key) FROM catalog_courses c WHERE {full}", [*values, *params]
    ).fetchone()[0])
    return rows, total


def _result(conn: sqlite3.Connection, rows: list[sqlite3.Row], total: int, limit: int,
            subject: str | None) -> dict[str, Any]:
    """Render ranked rows as one entry per course, whatever it is cross-listed as."""
    info = meta(conn)
    result: dict[str, Any] = {
        "courses": collapse_cross_listings(conn, rows, limit, subject),
        "total": total,
        "catalog_as_of": info.get("catalog_as_of", "unknown"),
        "offerings_as_of": info.get("offerings_as_of", "unknown"),
        "terms_known": terms_known(conn),
    }
    note = info.get("offerings_note", "").strip()
    if note:
        result["offerings_note"] = note
    return result


def collapse_cross_listings(conn: sqlite3.Connection, rows: list[sqlite3.Row], limit: int,
                            subject: str | None) -> list[dict[str, Any]]:
    """Keep one row per cross-listing group, naming the other codes on it.

    DATA C204, STS C204, and HISTORY C254 are one course; returning all three fills a
    third of a page of suggestions with the same class. The row shown is the one the
    student asked for when they filtered by subject, and otherwise the alphabetically
    first code, so the choice does not depend on which member the ranking happened to
    surface first.
    """
    wanted = (subject or "").strip().upper()
    chosen: dict[str, sqlite3.Row] = {}
    for row in rows:
        key = str(row["group_key"]) or f"{row['subject']} {row['number']}"
        current = chosen.get(key)
        if current is None or _preferred(row, current, wanted):
            chosen[key] = row

    ordered = [chosen[key] for key in list(chosen)[:limit]]
    rendered = []
    for row in ordered:
        course = format_course(conn, row, preview=True)
        others = group_members(conn, str(row["group_key"]), exclude=(str(row["subject"]), str(row["number"])))
        if others:
            course["also_listed_as"] = others
        rendered.append(course)
    return rendered


def _preferred(candidate: sqlite3.Row, current: sqlite3.Row, wanted_subject: str) -> bool:
    """Return whether *candidate* should represent its group instead of *current*."""
    if wanted_subject:
        if str(candidate["subject"]) == wanted_subject and str(current["subject"]) != wanted_subject:
            return True
        if str(current["subject"]) == wanted_subject:
            return False
    return (str(candidate["subject"]), str(candidate["number"])) < (str(current["subject"]), str(current["number"]))


def group_members(conn: sqlite3.Connection, group_key: str, *, exclude: tuple[str, str]) -> list[str]:
    """Return the other codes a course is listed under."""
    if not group_key:
        return []
    return [
        f"{row['subject']} {row['number']}"
        for row in conn.execute(
            "SELECT subject, number FROM catalog_courses WHERE group_key = ? ORDER BY subject, number",
            (group_key,),
        )
        if (str(row["subject"]), str(row["number"])) != exclude
    ]


def details(conn: sqlite3.Connection, subject: str, number: str) -> dict[str, Any] | None:
    """Return one catalog course in full, with the terms it is known to be offered."""
    row = conn.execute(
        "SELECT * FROM catalog_courses WHERE subject = ? AND number = ?",
        (subject.strip().upper(), number.strip()),
    ).fetchone()
    if row is None:
        row = conn.execute(
            "SELECT * FROM catalog_courses WHERE subject = ? AND UPPER(number) = ?",
            (subject.strip().upper(), number.strip().upper()),
        ).fetchone()
    if row is None:
        return None
    course = format_course(conn, row, preview=False)
    info = meta(conn)
    course["catalog_as_of"] = info.get("catalog_as_of", "unknown")
    course["offerings_as_of"] = info.get("offerings_as_of", "unknown")
    return course


def subjects(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """List every subject code with how many courses it has."""
    return [
        {"code": str(row["subject"]), "course_count": int(row["n"])}
        for row in conn.execute(
            "SELECT subject, COUNT(*) AS n FROM catalog_courses GROUP BY subject ORDER BY subject"
        )
    ]


def format_course(conn: sqlite3.Connection, row: sqlite3.Row, *, preview: bool) -> dict[str, Any]:
    """Render a catalog row for a tool payload."""
    units = str(row["units_min"] or "")
    if row["units_max"] and row["units_max"] != row["units_min"]:
        units = f"{units}-{row['units_max']}"

    course: dict[str, Any] = {
        "subject": str(row["subject"]),
        "number": str(row["number"]),
        "level": str(row["level"]),
        "title": str(row["title"]),
        "units": units,
    }
    if row["department"]:
        course["department"] = str(row["department"])

    description = str(row["description"] or "")
    if description:
        limit = SEARCH_PREVIEW if preview else DESCRIPTION_PREVIEW
        course["description"] = (
            _trim(description, limit) if preview and len(description) > limit else description
        )
    if not preview:
        if row["cross_listed"]:
            course["cross_listed"] = str(row["cross_listed"])
        if row["repeat_rules"]:
            course["repeat_rules"] = str(row["repeat_rules"])
        if row["offering_details"]:
            course["offering_details"] = str(row["offering_details"])
    if not row["in_printed_catalog"]:
        course["in_printed_catalog"] = False

    # In a list of ten suggestions the actionable fact is "offered, this many sections".
    # Who teaches it and how matters when choosing between sections, which is what
    # `check_offering` and `get_catalog_course` are for — and carrying it here costs
    # about 60 bytes a course, which is the difference between ten results and eight.
    offerings = [
        {
            "term": str(entry["term"]),
            "sections": int(entry["section_count"] or 0),
            **({} if preview else {
                **({"instructors": str(entry["instructors"])} if entry["instructors"] else {}),
                **({"modes": str(entry["instruction_modes"])} if entry["instruction_modes"] else {}),
            }),
        }
        for entry in conn.execute(
            "SELECT * FROM term_offerings WHERE subject = ? AND number = ? ORDER BY term",
            (row["subject"], row["number"]),
        )
    ]
    if offerings:
        course["offered_terms"] = offerings
    return course


# Berkeley course numbers can carry a letter prefix (C = cross-listed, W = web,
# N = summer, H = honors), so "INTEGBI C156" is subject INTEGBI, number C156 — not
# subject "INTEGBI C". Subjects are one to three words ("MEC ENG", "L & S").
COURSE_CODE = re.compile(
    r"^\s*([A-Za-z]+(?:[ &/-]+[A-Za-z]+){0,2}?)\s*[- ]?\s*([A-Za-z]{0,2}[0-9][0-9A-Za-z]*)\s*$"
)


def fit_previews(payload: dict[str, Any], budget: int, *, floor: int = MIN_PREVIEW) -> dict[str, Any]:
    """Shrink descriptions until a page of search results fits its byte budget.

    A list tool degrades better in fidelity than in completeness: losing twenty
    characters of every gist is a smaller loss than losing the tenth course entirely,
    which is what the generic `shrink` backstop would otherwise do. The longest
    descriptions are cut first, so short entries keep their whole text.
    """
    courses = payload.get("courses")
    if not isinstance(courses, list) or not courses:
        return payload

    def size() -> int:
        """Measure the payload the way the tool serialises it, not with default spacing."""
        return len(json.dumps(payload, default=str, separators=(",", ":")))

    while size() > budget:
        longest = max(courses, key=lambda c: len(str(c.get("description") or "")))
        text = str(longest.get("description") or "")
        if len(text) <= floor:
            break  # nothing left to give; `shrink` drops whole entries from here
        longest["description"] = _trim(text, max(floor, int(len(text) * 0.85)))
    return payload


ELLIPSIS: Final[str] = "..."


def _trim(text: str, limit: int) -> str:
    """Cut a description to *limit* characters total, ending on a word where possible.

    The limit includes the ellipsis, so a caller measuring the result against its budget
    gets the number it asked for.
    """
    if len(text) <= limit:
        return text
    window = text[: max(1, limit - len(ELLIPSIS))]
    cut = window.rfind(" ")
    return (window[:cut] if cut > limit // 2 else window).rstrip(" ,;:") + ELLIPSIS


def parse_course_code(code: str) -> tuple[str, str] | None:
    """Split ``"STAT 156"``, ``"COMPSCI 61A"``, or ``"INTEGBI C156"`` into subject and number."""
    match = COURSE_CODE.match(code or "")
    if not match:
        return None
    subject = " ".join(match.group(1).upper().split())
    return subject, match.group(2).strip().upper()


# -- public data updates ------------------------------------------------------


def _stamp_path() -> Path:
    """Return the file recording when we last checked for newer public data."""
    return home_dir() / "data_check"


def _last_check() -> float:
    """Return the epoch seconds of the last update check."""
    try:
        return float(_stamp_path().read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0.0


def _record_check() -> None:
    """Record that an update check just happened."""
    try:
        _stamp_path().parent.mkdir(parents=True, exist_ok=True)
        _stamp_path().write_text(str(datetime.now(UTC).timestamp()), encoding="utf-8")
    except OSError:  # pragma: no cover
        logger.debug("Could not record the data update check time.")


def maybe_update(*, enabled: bool, force: bool = False, path: Path | None = None) -> str | None:
    """Check GitHub for a newer public catalog snapshot, at most once a day.

    Returns a short message when something happened, ``None`` when it did nothing. This
    never fails a tool call: stale-but-working catalog data beats an error.
    """
    if not enabled:
        return None
    now = datetime.now(UTC).timestamp()
    if not force and now - _last_check() < UPDATE_INTERVAL_S:
        return None
    _record_check()

    try:
        import httpx

        response = httpx.get(MANIFEST_URL, timeout=UPDATE_TIMEOUT_S, follow_redirects=True)
        response.raise_for_status()
        manifest = response.json()
    except Exception:
        # Being offline, or the data file not being published yet, is an ordinary state:
        # the packaged snapshot still works. The check marker is already recorded above,
        # so a failure does not turn into a retry on every call.
        logger.debug("No newer catalog data available right now; keeping the current snapshot.")
        return None

    if not isinstance(manifest, dict):
        return None
    remote_as_of = str(manifest.get("catalog_as_of") or "")
    remote_hash = str(manifest.get("data_sha256") or "")
    if not remote_as_of or not remote_hash:
        return None

    target = path or catalog_db_path()
    try:
        with connect(target) as conn:
            local = meta(conn)
    except CatalogError:
        local = {}
    if local.get("data_sha256") == remote_hash:
        return None
    if local.get("catalog_as_of", "") >= remote_as_of:
        return None

    return _download_and_rebuild(manifest, remote_as_of, remote_hash, target)


def _download_and_rebuild(manifest: dict[str, Any], as_of: str, expected_hash: str, target: Path) -> str | None:
    """Fetch the published data asset, verify its hash, and rebuild the index."""
    url = str(manifest.get("asset_url") or ASSET_URL_TEMPLATE.format(date=as_of))
    try:
        import httpx

        with httpx.stream("GET", url, timeout=UPDATE_TIMEOUT_S, follow_redirects=True) as response:
            response.raise_for_status()
            buffer = bytearray()
            for chunk in response.iter_bytes():
                buffer.extend(chunk)
                if len(buffer) > MAX_ASSET_BYTES:
                    logger.warning("Catalog data asset exceeded the size limit; ignoring it.")
                    return None
    except Exception as exc:
        logger.info("Could not download the catalog data asset: %s", type(exc).__name__)
        return None

    digest = hashlib.sha256(bytes(buffer)).hexdigest()
    if digest != expected_hash:
        logger.warning("Catalog data asset failed its SHA-256 check; keeping the existing catalog.")
        return None

    staging = home_dir() / "data-staging"
    try:
        _extract_asset(bytes(buffer), staging)
        counts = build(target, source_dir=staging)
        # Record what was actually verified, not what the archive says about itself.
        # Trusting the inner manifest would make a mislabelled asset re-download daily.
        _stamp(target, {"catalog_as_of": as_of, "data_sha256": expected_hash})
    except Exception as exc:
        logger.warning("Could not rebuild the catalog from the downloaded data: %s", type(exc).__name__)
        return None
    finally:
        _remove_tree(staging)

    return f"Updated the Berkeley catalog to the {as_of} snapshot ({counts['courses']} courses)."


def _stamp(target: Path, values: dict[str, str]) -> None:
    """Overwrite provenance fields in a built catalog."""
    with connect(target) as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        conn.commit()


def _extract_asset(body: bytes, destination: Path) -> None:
    """Unpack the data asset, refusing any member that escapes the destination."""
    _remove_tree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            name = Path(member.name).name
            if name not in {*_CSV_FILES, "term_offerings.csv", "catalog_meta.json"}:
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            (destination / name).write_bytes(extracted.read(MAX_ASSET_BYTES))


def _remove_tree(path: Path) -> None:
    """Delete a staging directory and its files."""
    if not path.exists():
        return
    for child in path.iterdir():
        if child.is_file():
            child.unlink()
    path.rmdir()
