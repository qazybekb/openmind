#!/usr/bin/env python3
"""Rebuild the public Berkeley course data that ships with OpenMind.

Course data changes on the university's calendar, not on ours. This script runs in CI
so a student's catalog stays current without waiting for a release — and so the project
keeps working when nobody is maintaining it.

Three things happen here:

1. **Catalogs.** Both Coursedog catalogs are exported as CSV using the same request the
   site's own "Download CSV" button makes. No login, no API key. Catalog ids change each
   academic year and are read from each catalog page's payload.
2. **Offerings.** The class schedule is crawled for the current and next term, one
   subject at a time, politely. This is what makes "can I take it this semester"
   answerable — `Terms Offered` is empty for every row in the catalog export.
3. **The union rule.** A course that is scheduled but hidden by the catalog's default
   filters (STAT 156 is one) is pulled from an unfiltered export and flagged
   ``In Printed Catalog = 0``. Being offered matters more than being printed.

When the class schedule refuses to answer at all — it returns HTTP 403 to GitHub-hosted
runner IP ranges — the catalogs are still refreshed, the previous offerings snapshot is
kept untouched, and the manifest says so. A catalog one day old beats a job that fails
every day and refreshes nothing.

Nothing is written unless the data actually changed, so an unchanged run produces no
commit.

    python3 scripts/refresh_catalog.py --out src/openmind/data
    python3 scripts/refresh_catalog.py --out data --skip-offerings   # catalogs only
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openmind import schedule  # noqa: E402

API = "https://app.coursedog.com/api/v1"
SCHOOL = "ucberkeley_peoplesoft"
CATALOG_PAGES = {
    "undergraduate": "https://undergraduate.catalog.berkeley.edu/courses",
    "graduate": "https://graduate.catalog.berkeley.edu/courses",
}
UA = "openmind-berkeley catalog refresh (+https://github.com/qazybekb/openmind)"
SCHEDULE_HOST = "classes.berkeley.edu"

# Each catalog site applies its own default department exclusions; these are the ones
# read from the sites' own payloads.
CATALOG_DEFAULTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "undergraduate": ("Undergraduate", ("LAW", "NONUCB", "UCEAP")),
    "graduate": ("Graduate", ("GGAGECH", "NONUCB")),
}

MIN_ROWS = {"undergraduate": 5_000, "graduate": 3_000}
MIN_SUBJECTS = 200
# A term with fewer offerings than this is a failed crawl, not a quiet semester:
# Fall 2026 has about 2,700 courses scheduled.
MIN_OFFERINGS_PER_TERM = 500
# Above this share of failed subjects the snapshot is too patchy to publish, even with
# the previous rows carried forward.
MAX_FAILURE_FRACTION = 0.10


def log(message: str) -> None:
    """Report progress on stderr so stdout stays machine-readable."""
    print(message, file=sys.stderr, flush=True)


# -- Coursedog export ----------------------------------------------------------


def _field(name: str, group: str, kind: str, value: Any, input_type: str = "select") -> dict[str, Any]:
    """Build one Coursedog filter clause."""
    return {"id": f"{name}-{group}", "condition": "field", "name": name, "inputType": input_type,
            "group": group, "type": kind, "value": value, "customField": False}


def build_filters(career: str | None, excluded_departments: tuple[str, ...]) -> dict[str, Any]:
    """The catalog site's own default filters, plus an optional career restriction."""
    filters = [
        _field("status", "course", "is", "Active"),
        *[_field("departments", "course", "doesNotContain", [code]) for code in excluded_departments],
        _field("catalogPrint", "course", "is", True, input_type="boolean"),
        _field("courseApproved", "course", "is", "Approved"),
    ]
    if career:
        filters.append(_field("career", "course", "is", career))
    return {"condition": "and", "filters": filters}


def unfiltered_filters() -> dict[str, Any]:
    """Everything active and approved, including courses kept out of the printed catalog."""
    return {"condition": "and", "filters": [
        _field("status", "course", "is", "Active"),
        _field("departments", "course", "doesNotContain", ["NONUCB"]),
        _field("courseApproved", "course", "is", "Approved"),
    ]}


def _get(url: str, timeout: int = 120) -> str:
    """Fetch a URL as text."""
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8", "replace")


def discover_catalog_ids() -> dict[str, str]:
    """Read the active catalog id for each site from its own page payload.

    The ids roll over every academic year. Reading them rather than hard-coding them is
    what lets this script keep working after the maintainer stops watching it.
    """
    ids: dict[str, str] = {}
    for name, url in CATALOG_PAGES.items():
        page = _get(url)
        match = re.search(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', page, re.S)
        if not match:
            raise SystemExit(f"{name}: could not find the catalog payload on {url}")
        payload = json.loads(match.group(1))
        for node in payload:
            if isinstance(node, dict) and "activeCatalog" in node and "catalogDisplayName" in node:
                ids[name] = payload[node["activeCatalog"]]
                log(f"{name}: {payload[node['catalogDisplayName']]} -> {ids[name]}")
                break
        else:
            raise SystemExit(f"{name}: no activeCatalog in the payload from {url}")
    return ids


def export_csv(catalog_id: str, filters: dict[str, Any]) -> list[dict[str, str]]:
    """Run the catalog's own CSV export and parse it."""
    url = (f"{API}/ca/{SCHOOL}/catalogs/{catalog_id}/courses/csv/$filters"
           "?orderBy=catalogDisplayName&ignoreEffectiveDating=false")
    request = urllib.request.Request(
        url, data=json.dumps(filters).encode(), method="POST",
        headers={"User-Agent": UA, "Content-Type": "application/json"},
    )
    text = urllib.request.urlopen(request, timeout=300).read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


# -- offerings -----------------------------------------------------------------


def current_and_future_terms(terms: list[schedule.Facet], today: date, limit: int) -> list[schedule.Facet]:
    """Keep the term in progress and anything after it, oldest first.

    Crawling a past term would tell a student a course is "offered Spring 2026" months
    after enrolment closed. The Registrar posts one term ahead at most, so this is
    usually one or two terms — and Spring 2027 joins on its own the day it appears.
    """
    season = 2 if today.month >= 8 else (1 if today.month >= 6 else 0)
    floor = (today.year, season)
    upcoming = [term for term in schedule.full_semesters(terms) if schedule.term_sort_key(term.name) >= floor]
    return sorted(upcoming, key=lambda t: schedule.term_sort_key(t.name))[:limit]


def crawl_offerings(subjects: list[str], terms: list[schedule.Facet], delay: float,
                    limit: int | None = None) -> tuple[list[dict[str, str]], list[tuple[str, str, str]]]:
    """Crawl the class schedule for each subject in each term.

    Returns the rows found and the ``(term, subject, reason)`` triples that failed. The
    caller decides what to do about the failures; this function does not get to make a
    thin snapshot look complete.
    """
    rows: list[dict[str, str]] = []
    failures: list[tuple[str, str, str]] = []
    targets = subjects[:limit] if limit else subjects

    for term in terms:
        log(f"term {term.name} (facet {term.facet_id}, {term.count} sections)")
        found = 0
        for position, subject in enumerate(targets, start=1):
            try:
                sections = schedule.crawl_subject(subject, term.facet_id, delay=delay)
            except schedule.ScheduleError as exc:
                failures.append((term.name, subject, str(exc)))
                continue
            offerings = schedule.collapse(sections, term.name)
            rows.extend(offering.to_row() for offering in offerings)
            found += len(offerings)
            if position % 25 == 0:
                log(f"  {position}/{len(targets)} subjects, {found} courses so far")
        log(f"  {term.name}: {found} courses offered")
    return rows, failures


def read_previous_offerings(out: Path) -> list[dict[str, str]]:
    """Read the offerings snapshot already on disk, if there is one."""
    path = out / "term_offerings.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_previous_manifest(out: Path) -> dict[str, Any]:
    """Read the manifest already on disk, if there is a readable one."""
    path = out / "catalog_meta.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def unreachable_note(exc: Exception) -> str:
    """Say why the offerings were not refreshed, naming the status when there is one.

    GitHub-hosted runners get HTTP 403 from the class schedule, so for the scheduled job
    this is the ordinary state rather than a rare failure. It has to read as a fact about
    the data a student is holding, not as a stack trace.
    """
    status = re.search(r"HTTP (\d{3})", str(exc))
    if status:
        reason = f"{SCHEDULE_HOST} returned HTTP {status.group(1)}"
    else:
        reason = f"{SCHEDULE_HOST} could not be reached ({str(exc).strip().rstrip('.') or type(exc).__name__})"
    return f"offerings not refreshed: {reason}; previous snapshot kept"


def carried_offerings(manifest: dict[str, Any], rows: list[dict[str, str]]) -> dict[str, Any]:
    """Describe the offerings snapshot being kept, from the manifest that shipped it.

    A run that does not crawl still packages the previous ``term_offerings.csv`` into the
    release asset. Writing today's date and zero counts would tell every client the
    snapshot has no offerings at all — the one thing the file on disk proves is false.
    """
    terms = manifest.get("terms_known") or sorted({row["term"] for row in rows if row.get("term")})
    carried: dict[str, Any] = {
        "offerings_as_of": str(manifest.get("offerings_as_of") or ""),
        "terms_known": [str(term) for term in terms],
        "offering_count": int(manifest.get("offering_count") or len(rows)),
    }
    stale = manifest.get("stale_subjects")
    if stale:
        carried["stale_subjects"] = [str(subject) for subject in stale]
    return carried


def carry_forward(rows: list[dict[str, str]], previous: list[dict[str, str]],
                  failures: list[tuple[str, str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    """Reuse the last good rows for subjects whose crawl failed this time.

    A subject that failed is unknown, not empty. Dropping its rows would tell every
    student in that department that none of their courses are offered — the exact
    failure this whole snapshot exists to avoid. Carrying the previous rows and naming
    the subject as stale is honest; silently publishing a hole is not.
    """
    stale: list[str] = []
    by_key = {(row["term"], row["subject"]) for row in rows}
    for term, subject, _ in failures:
        if (term, subject) in by_key:
            continue
        recovered = [row for row in previous if row.get("term") == term and row.get("subject") == subject]
        if recovered:
            rows.extend(recovered)
            stale.append(f"{subject} ({term})")
    return rows, sorted(set(stale))


def coverage_problems(rows: list[dict[str, str]], previous: list[dict[str, str]],
                      terms: list[schedule.Facet], failures: list[tuple[str, str, str]],
                      subject_count: int) -> list[str]:
    """Return the reasons this snapshot must not be published, if any."""
    problems: list[str] = []
    fresh_terms = {term.name for term in terms}

    for term in fresh_terms:
        count = sum(1 for row in rows if row.get("term") == term)
        if count < MIN_OFFERINGS_PER_TERM:
            problems.append(f"{term}: only {count} course offerings, expected at least {MIN_OFFERINGS_PER_TERM}")

    for term in fresh_terms:
        expected = {row["subject"] for row in previous if row.get("term") == term}
        if not expected:
            continue
        have = {row["subject"] for row in rows if row.get("term") == term}
        lost = sorted(expected - have)
        if lost:
            problems.append(
                f"{term}: {len(lost)} subject(s) that had offerings last time have none now "
                f"and could not be recovered: {', '.join(lost[:8])}"
            )

    if subject_count and len(failures) > subject_count * len(fresh_terms) * MAX_FAILURE_FRACTION:
        problems.append(
            f"{len(failures)} subject crawls failed, over the {MAX_FAILURE_FRACTION:.0%} tolerance — "
            "the class schedule is probably down or has changed shape"
        )
    return problems


# -- writing -------------------------------------------------------------------


OFFERING_FIELDS = ["subject", "number", "term", "section_count", "instruction_modes", "instructors"]


def catalog_order(fieldnames: list[str]):
    """Return a sort key that puts catalog rows in one order whatever order they arrived in.

    Coursedog's export serves the same rows in a different order from one day to the
    next. On 2026-09-06 the daily job republished a graduate catalog whose every row
    had moved and none had changed: a new asset, a new manifest commit, and a download
    for every student for nothing. Sorting on subject, number, then the whole row makes
    "unchanged" mean what it says.
    """
    lead = [name for name in ("Subject", "Course Number") if name in fieldnames]
    rest = [name for name in fieldnames if name not in lead]

    def key(row: dict[str, str]) -> tuple[str, ...]:
        return tuple(str(row.get(name, "") or "") for name in (*lead, *rest))

    return key


def render_csv(rows: list[dict[str, str]], fieldnames: list[str]) -> str:
    """Render rows as CSV text in a stable order, whatever order they arrived in."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(sorted(rows, key=catalog_order(fieldnames)))
    return buffer.getvalue()


def already_on_disk(pending: dict[Path, str]) -> bool:
    """Return whether every file this run would write already holds exactly that text."""
    return all(path.exists() and path.read_bytes() == text.encode("utf-8") for path, text in pending.items())


def write_all(pending: dict[Path, str]) -> None:
    """Write the rendered files as UTF-8, leaving their line endings exactly as rendered."""
    for path, text in pending.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")


def content_hash(paths: list[Path]) -> str:
    """Hash the data files so an unchanged run can stop before committing anything."""
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda p: p.name):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    """Refresh the packaged Berkeley course data."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="src/openmind/data", help="directory to write the data files into")
    parser.add_argument("--skip-offerings", action="store_true", help="export catalogs only")
    parser.add_argument("--terms", type=int, default=2, help="how many upcoming terms to crawl")
    parser.add_argument("--delay", type=float, default=schedule.POLITE_DELAY_S, help="seconds between page requests")
    parser.add_argument("--subject-limit", type=int, help="crawl only the first N subjects (for smoke runs)")
    parser.add_argument("--allow-coverage-loss", action="store_true",
                        help="publish even when a subject that had offerings last time now has none")
    args = parser.parse_args()

    out = Path(args.out)
    previous_meta = read_previous_manifest(out)
    previous_offerings = read_previous_offerings(out)

    log("== catalogs ==")
    ids = discover_catalog_ids()
    catalogs: dict[str, list[dict[str, str]]] = {}
    for level, (career, exclusions) in CATALOG_DEFAULTS.items():
        rows = export_csv(ids[level], build_filters(career, exclusions))
        if len(rows) < MIN_ROWS[level]:
            raise SystemExit(f"{level}: only {len(rows)} rows, expected at least {MIN_ROWS[level]}. Refusing to ship.")
        catalogs[level] = rows
        log(f"{level}: {len(rows)} rows, {len({r['Subject'] for r in rows})} subjects")

    subjects = sorted({row["Subject"] for rows in catalogs.values() for row in rows if row.get("Subject")})
    if len(subjects) < MIN_SUBJECTS:
        raise SystemExit(f"only {len(subjects)} subjects, expected at least {MIN_SUBJECTS}. Refusing to ship.")

    offerings: list[dict[str, str]] = []
    terms: list[schedule.Facet] = []
    failures: list[tuple[str, str, str]] = []
    stale_subjects: list[str] = []
    note = ""
    if args.skip_offerings:
        note = "offerings not refreshed: --skip-offerings was requested; previous snapshot kept"
    else:
        log("== offerings ==")
        try:
            # `schedule.fetch` funnels every transport failure into ScheduleError, so this
            # covers a refused connection as well as an HTTP status.
            terms = current_and_future_terms(schedule.list_terms(), date.today(), args.terms)
            if not terms:
                raise SystemExit("the class schedule listed no current or upcoming terms. Refusing to ship.")
            offerings, failures = crawl_offerings(subjects, terms, args.delay, args.subject_limit)
        except schedule.ScheduleError as exc:
            # Not a coverage refusal. Nothing was learned about the offerings, so the
            # snapshot on disk is still the best available and is left exactly as it is
            # while the catalogs — which come from a different site — still refresh.
            log(f"the class schedule could not be read: {exc}")
            note = unreachable_note(exc)
            log(note)
            terms, offerings, failures = [], [], []
        else:
            log(f"{len(offerings)} course-term offerings across {len(terms)} term(s)")
            if failures:
                log(f"{len(failures)} subject crawl(s) failed: {[f'{t} {s}' for t, s, _ in failures[:5]]}")
                offerings, stale_subjects = carry_forward(offerings, previous_offerings, failures)
                if stale_subjects:
                    log(f"carried forward the previous rows for {len(stale_subjects)} subject(s)")

            crawled = subjects[: args.subject_limit] if args.subject_limit else subjects
            blocking = coverage_problems(offerings, previous_offerings, terms, failures, len(crawled))
            if blocking and args.allow_coverage_loss:
                for problem in blocking:
                    log(f"coverage warning (overridden by --allow-coverage-loss): {problem}")
                blocking = []
            if blocking:
                for problem in blocking:
                    log(f"REFUSING TO PUBLISH: {problem}")
                log("Nothing was written. The existing snapshot is still the best available.")
                log("If this is a real change rather than an outage, re-run with --allow-coverage-loss.")
                return 1

    # A course that is scheduled but hidden by the catalog's default filters still
    # matters — it is one a student can actually enrol in. When the offerings were not
    # refreshed, the rows on disk are the ones that will ship, so they decide the union:
    # dropping STAT 156 from the catalogs because nobody crawled today would be a loss.
    scheduled = {(row["subject"], row["number"]) for row in (previous_offerings if note else offerings)}
    known = {(row.get("Subject", ""), row.get("Course Number", "")) for rows in catalogs.values() for row in rows}
    missing = scheduled - known
    if missing:
        log(f"== union: {len(missing)} scheduled course(s) are not in the filtered catalogs ==")
        extra = export_csv(ids["undergraduate"], unfiltered_filters())
        recovered = 0
        for row in extra:
            key = (row.get("Subject", ""), row.get("Course Number", ""))
            if key not in missing:
                continue
            row["In Printed Catalog"] = "0"
            level = "graduate" if str(row.get("Career", "")).lower().startswith("grad") else "undergraduate"
            catalogs[level].append(row)
            missing.discard(key)
            recovered += 1
        log(f"recovered {recovered} course(s); {len(missing)} still unmatched")

    log("== writing ==")
    pending: dict[Path, str] = {}
    for level, rows in catalogs.items():
        for row in rows:
            row.setdefault("In Printed Catalog", "1")
        fieldnames = list(rows[0].keys())
        if "In Printed Catalog" not in fieldnames:
            fieldnames.append("In Printed Catalog")
        path = out / f"{level}_courses.csv"
        pending[path] = render_csv(rows, fieldnames)
        log(f"{path}: {len(rows)} rows")

    if not note:
        path = out / "term_offerings.csv"
        pending[path] = render_csv(offerings, OFFERING_FIELDS)
        log(f"{path}: {len(offerings)} rows")

    # "Changed" is a claim about the data this run rebuilt. A run that deliberately left
    # the offerings alone must not be called changed because of a file it never touched,
    # and an unchanged run must not rewrite anything at all — including the manifest,
    # whose date would otherwise be the only thing that ever differed.
    manifest_path = out / "catalog_meta.json"
    if manifest_path.exists() and already_on_disk(pending):
        log("no change since the last run; nothing to publish")
        print("unchanged")
        return 0

    today = date.today().isoformat()
    manifest: dict[str, Any] = {
        "catalog_as_of": today,
        "offerings_as_of": today if offerings else "",
        "terms_known": [term.name for term in terms],
        "course_count": sum(len(rows) for rows in catalogs.values()),
        "subject_count": len(subjects),
        "offering_count": len(offerings),
        "asset_url": (
            f"https://github.com/qazybekb/openmind/releases/download/data-{today}/catalog-{today}.tar.gz"
        ),
        "data_sha256": "",
    }
    if note:
        # The manifest ships with the offerings file, so it must describe the snapshot
        # that is actually in the asset rather than the crawl that did not happen.
        manifest.update(carried_offerings(previous_meta, previous_offerings))
        manifest["offerings_note"] = note
    elif stale_subjects:
        # Named rather than hidden: a reader can tell which departments are a day old.
        manifest["stale_subjects"] = stale_subjects

    write_all(pending)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    log(f"content hash {content_hash([*pending, manifest_path])}")
    print("changed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.URLError as exc:  # pragma: no cover - network failure in CI
        log(f"network error: {exc}")
        raise SystemExit(2) from exc
