"""The parts of the data-refresh job that can be tested without touching the network."""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import shutil
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from openmind import catalog, schedule
from openmind.schedule import Facet

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "src" / "openmind" / "data"
DATA_FILES = ("undergraduate_courses.csv", "graduate_courses.csv", "term_offerings.csv", "catalog_meta.json")

# What classes.berkeley.edu says to a GitHub-hosted runner, and what the manifest must
# say about it afterwards.
BLOCKED = schedule.ScheduleError("The Berkeley class schedule returned HTTP 403.")
NOTE_403 = "offerings not refreshed: classes.berkeley.edu returned HTTP 403; previous snapshot kept"


@pytest.fixture(scope="module")
def refresh():
    """Import scripts/refresh_catalog.py, which is not part of the package."""
    spec = importlib.util.spec_from_file_location("refresh_catalog", REPO_ROOT / "scripts" / "refresh_catalog.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["refresh_catalog"] = module
    spec.loader.exec_module(module)
    return module


TERMS = [
    Facet("8588", "Fall 2026", 6134),
    Facet("8579", "Spring 2026", 5000),
    Facet("7171", "Fall 2016", 7513),
    Facet("9000", "Spring 2027", 10),
    Facet("8580", "Summer Sessions 2026", 941),
    Facet("8581", "12W: Week May 26-Aug 14", 141),
]


def test_a_past_term_is_never_crawled(refresh):
    """"Offered Spring 2026" is worse than no answer once Spring 2026 is over."""
    chosen = refresh.current_and_future_terms(TERMS, date(2026, 9, 5), 2)
    assert [term.name for term in chosen] == ["Fall 2026", "Spring 2027"]


def test_the_term_in_progress_is_still_crawled(refresh):
    chosen = refresh.current_and_future_terms(TERMS, date(2026, 3, 1), 2)
    assert [term.name for term in chosen] == ["Spring 2026", "Fall 2026"]


def test_summer_falls_back_to_the_next_full_semester(refresh):
    """In June there is no Spring left to plan for, so Fall is what matters."""
    chosen = refresh.current_and_future_terms(TERMS, date(2026, 6, 15), 2)
    assert [term.name for term in chosen] == ["Fall 2026", "Spring 2027"]


def test_a_newly_posted_term_joins_on_its_own(refresh):
    """Spring 2027 appears the day the Registrar posts it, with no code change."""
    without = [t for t in TERMS if t.name != "Spring 2027"]
    assert [t.name for t in refresh.current_and_future_terms(without, date(2026, 9, 5), 2)] == ["Fall 2026"]
    assert "Spring 2027" in [t.name for t in refresh.current_and_future_terms(TERMS, date(2026, 9, 5), 2)]


def test_sub_sessions_are_not_treated_as_semesters(refresh):
    chosen = refresh.current_and_future_terms(TERMS, date(2026, 1, 1), 5)
    assert "12W: Week May 26-Aug 14" not in [term.name for term in chosen]
    assert "Summer Sessions 2026" not in [term.name for term in chosen]


def test_the_export_filters_match_the_catalog_sites_own_defaults(refresh):
    undergraduate = refresh.build_filters(*refresh.CATALOG_DEFAULTS["undergraduate"])
    names = [clause["name"] for clause in undergraduate["filters"]]
    assert names.count("departments") == 3  # LAW, NONUCB, UCEAP
    assert "catalogPrint" in names and "courseApproved" in names and "career" in names
    career = next(c for c in undergraduate["filters"] if c["name"] == "career")
    assert career["value"] == "Undergraduate"


def test_the_unfiltered_export_drops_the_printed_catalog_restriction(refresh):
    """That restriction is what hides STAT 156, which is really offered."""
    names = [clause["name"] for clause in refresh.unfiltered_filters()["filters"]]
    assert "catalogPrint" not in names
    assert "career" not in names
    assert "status" in names and "courseApproved" in names


def test_rendered_catalogs_do_not_depend_on_the_export_order(refresh):
    """Coursedog reorders its export between days; identical rows must render identically."""
    fieldnames = ["Subject", "Course Number", "Course Title", "In Printed Catalog"]
    rows = [
        {"Subject": "MECENG", "Course Number": "253", "Course Title": "Optics", "In Printed Catalog": "1"},
        {"Subject": "ENGIN", "Course Number": "238E", "Course Title": "Robust Optimization", "In Printed Catalog": "1"},
        {"Subject": "ENGIN", "Course Number": "238E", "Course Title": "Robust Optimization", "In Printed Catalog": "0"},
    ]
    forward = refresh.render_csv(rows, fieldnames)
    backward = refresh.render_csv(list(reversed(rows)), fieldnames)
    assert forward == backward
    assert forward.splitlines()[1].startswith("ENGIN,238E,Robust Optimization,0")


def test_the_content_hash_is_stable_and_order_independent(refresh, tmp_path: Path):
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    digest = refresh.content_hash([first, second])
    assert digest == refresh.content_hash([second, first])

    second.write_text("changed", encoding="utf-8")
    assert digest != refresh.content_hash([first, second])


# -- the class schedule refusing to answer ---------------------------------------
#
# classes.berkeley.edu returns HTTP 403 to GitHub Actions IP ranges. The same URLs
# answer 200 from a laptop, so it is an origin block rather than an outage, and it is
# the state the scheduled job runs in every day. Failing would freeze the catalogs too,
# and those come from a different site that answers fine.


@pytest.fixture(scope="module")
def packaged_catalogs():
    """The real catalog exports, read once — the export step is stubbed with these."""
    return [catalog._read_csv("undergraduate_courses.csv"), catalog._read_csv("graduate_courses.csv")]


@pytest.fixture(scope="module")
def shipped_manifest() -> dict:
    """The manifest that ships with the package, describing the offerings on disk."""
    return json.loads((DATA_DIR / "catalog_meta.json").read_text(encoding="utf-8"))


def seeded(tmp_path: Path) -> Path:
    """An output directory holding copies of the four data files the project ships."""
    target = tmp_path / "data"
    target.mkdir()
    for name in DATA_FILES:
        shutil.copy2(DATA_DIR / name, target / name)
    return target


def todays_catalogs(packaged: list[list[dict[str, str]]]) -> list[list[dict[str, str]]]:
    """Today's export, holding one course the snapshot on disk does not have yet.

    Three entries because a scheduled course missing from the filtered catalogs sends the
    script back for the unfiltered export.
    """
    undergraduate, graduate = packaged
    fresh = [*undergraduate, {**undergraduate[0], "Subject": "NEWSUBJ", "Course Number": "1",
                              "Course Title": "A Course Added Today"}]
    return [fresh, graduate, fresh]


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a written CSV without letting the platform rewrite its line endings."""
    return list(csv.DictReader(io.StringIO(path.read_bytes().decode("utf-8"), newline="")))


def run_refresh(refresh, exports, target: Path, *, terms_error=None, crawl_error=None, extra_args=()):
    """Run the script with both sites stubbed, returning (status, stdout, stderr)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    copies = [[dict(row) for row in rows] for rows in exports]
    with patch.object(refresh, "discover_catalog_ids", return_value={"undergraduate": "u", "graduate": "g"}), \
         patch.object(refresh, "export_csv", side_effect=copies), \
         patch.object(refresh.schedule, "list_terms",
                      side_effect=terms_error or (lambda: [Facet("8588", "Fall 2026", 6134)])), \
         patch.object(refresh, "crawl_offerings", side_effect=crawl_error or (lambda *a, **k: ([], []))), \
         patch.object(sys, "argv", ["refresh_catalog", "--out", str(target), *extra_args]), \
         redirect_stdout(stdout), redirect_stderr(stderr):
        status = refresh.main()
    return status, stdout.getvalue().strip(), stderr.getvalue()


def test_a_blocked_schedule_still_refreshes_the_catalogs(refresh, packaged_catalogs, tmp_path: Path):
    """A job that fails on the 403 would leave the catalog stale as well as the offerings."""
    target = seeded(tmp_path)
    before = (target / "term_offerings.csv").read_bytes()

    status, stdout, stderr = run_refresh(refresh, todays_catalogs(packaged_catalogs), target, terms_error=BLOCKED)

    assert status == 0 and stdout == "changed"
    assert (target / "term_offerings.csv").read_bytes() == before, "the kept snapshot must be untouched"
    assert "403" in stderr
    assert "REFUSING TO PUBLISH" not in stderr, "an unreachable site is not a coverage refusal"
    manifest = json.loads((target / "catalog_meta.json").read_text(encoding="utf-8"))
    assert manifest["catalog_as_of"] == date.today().isoformat()
    assert manifest["offerings_note"] == NOTE_403


def test_the_manifest_describes_the_offerings_that_actually_ship(refresh, packaged_catalogs, shipped_manifest,
                                                                 tmp_path: Path):
    """The kept file goes into the release asset, so calling it empty would be a lie."""
    target = seeded(tmp_path)

    status, _, _ = run_refresh(refresh, todays_catalogs(packaged_catalogs), target, terms_error=BLOCKED)

    manifest = json.loads((target / "catalog_meta.json").read_text(encoding="utf-8"))
    kept = read_rows(target / "term_offerings.csv")
    assert status == 0
    assert manifest["offerings_as_of"] == shipped_manifest["offerings_as_of"]
    assert manifest["terms_known"] == shipped_manifest["terms_known"] == sorted({row["term"] for row in kept})
    assert manifest["offering_count"] == shipped_manifest["offering_count"] == len(kept)


def test_a_blocked_run_whose_catalogs_did_not_change_writes_nothing(refresh, packaged_catalogs, tmp_path: Path):
    """Otherwise every day's job commits a manifest claiming data that did not move."""
    target = seeded(tmp_path)
    before = {name: (target / name).read_bytes() for name in DATA_FILES}

    status, stdout, _ = run_refresh(refresh, [*packaged_catalogs, *packaged_catalogs], target, terms_error=BLOCKED)

    assert status == 0 and stdout == "unchanged"
    assert {name: (target / name).read_bytes() for name in DATA_FILES} == before


def test_a_crawl_that_dies_part_way_degrades_rather_than_failing(refresh, packaged_catalogs, shipped_manifest,
                                                                 tmp_path: Path):
    """The term list answering is no guarantee the pages behind it will."""
    target = seeded(tmp_path)
    before = (target / "term_offerings.csv").read_bytes()

    status, stdout, _ = run_refresh(
        refresh, todays_catalogs(packaged_catalogs), target,
        crawl_error=schedule.ScheduleError("Could not reach the Berkeley class schedule."),
    )

    assert status == 0 and stdout == "changed"
    assert (target / "term_offerings.csv").read_bytes() == before
    manifest = json.loads((target / "catalog_meta.json").read_text(encoding="utf-8"))
    assert manifest["offerings_note"].startswith("offerings not refreshed: classes.berkeley.edu could not be reached")
    assert manifest["offering_count"] == shipped_manifest["offering_count"]


def test_skipping_the_crawl_carries_the_previous_offerings_forward(refresh, packaged_catalogs, shipped_manifest,
                                                                   tmp_path: Path):
    """`--skip-offerings` leaves the file in place, so the manifest must still describe it."""
    target = seeded(tmp_path)

    status, stdout, _ = run_refresh(refresh, todays_catalogs(packaged_catalogs), target,
                                    extra_args=("--skip-offerings",))

    assert status == 0 and stdout == "changed"
    manifest = json.loads((target / "catalog_meta.json").read_text(encoding="utf-8"))
    assert manifest["offerings_as_of"] == shipped_manifest["offerings_as_of"]
    assert manifest["terms_known"] == shipped_manifest["terms_known"]
    assert manifest["offering_count"] == shipped_manifest["offering_count"]
    assert "--skip-offerings" in manifest["offerings_note"]


def test_a_course_only_the_schedule_knows_about_survives_a_blocked_run(refresh, packaged_catalogs, tmp_path: Path):
    """STAT 156 is hidden by the catalog's own filters and is in the snapshot only
    because it is scheduled. Deciding the union from an empty crawl would drop it."""
    target = seeded(tmp_path)
    undergraduate, graduate = packaged_catalogs
    filtered = [row for row in undergraduate if (row["Subject"], row["Course Number"]) != ("STAT", "156")]

    status, _, stderr = run_refresh(refresh, [filtered, graduate, undergraduate], target, terms_error=BLOCKED)

    assert status == 0
    assert "== union" in stderr
    written = read_rows(target / "undergraduate_courses.csv")
    recovered = [row for row in written if (row["Subject"], row["Course Number"]) == ("STAT", "156")]
    assert recovered, "a scheduled course must not fall out of the catalogs on a catalogs-only run"
    assert recovered[0]["In Printed Catalog"] == "0"
