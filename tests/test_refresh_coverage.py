"""The refresh job must not publish a snapshot it knows is incomplete.

A crawl that half-failed and shipped anyway would tell every student in the affected
departments that none of their courses are offered. That is worse than shipping nothing,
so the job refuses, exits non-zero, and leaves the previous snapshot in place.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pytest

from openmind import catalog, schedule

REPO_ROOT = Path(__file__).resolve().parents[1]
FIELDS = ["subject", "number", "term", "section_count", "instruction_modes", "instructors"]
TERM = "Fall 2026"


@pytest.fixture(scope="module")
def refresh():
    spec = importlib.util.spec_from_file_location("refresh_catalog", REPO_ROOT / "scripts" / "refresh_catalog.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["refresh_catalog"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def packaged_catalogs():
    """The real catalog CSVs, read once — the export step is stubbed with these."""
    return [catalog._read_csv("undergraduate_courses.csv"), catalog._read_csv("graduate_courses.csv")]


def offerings(subject: str, count: int, term: str = TERM) -> list[dict[str, str]]:
    return [
        {"subject": subject, "number": str(100 + n), "term": term, "section_count": "1",
         "instruction_modes": "In-Person Instruction", "instructors": "A Lecturer"}
        for n in range(count)
    ]


def seed_previous(target: Path, rows: list[dict[str, str]]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    with (target / "term_offerings.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def run_refresh(refresh, packaged_catalogs, target: Path, crawl_result, extra_args=()):
    """Run the script with the network stubbed out, returning (status, stdout, stderr)."""
    stdout, stderr = io.StringIO(), io.StringIO()
    argv = ["refresh_catalog", "--out", str(target), *extra_args]
    with patch.object(refresh, "discover_catalog_ids", return_value={"undergraduate": "u", "graduate": "g"}), \
         patch.object(refresh, "export_csv", side_effect=list(packaged_catalogs) * 3), \
         patch.object(refresh.schedule, "list_terms", return_value=[schedule.Facet("8588", TERM, 6134)]), \
         patch.object(refresh, "crawl_offerings", return_value=crawl_result), \
         patch.object(sys, "argv", argv), \
         redirect_stdout(stdout), redirect_stderr(stderr):
        status = refresh.main()
    return status, stdout.getvalue().strip(), stderr.getvalue()


PREVIOUS = offerings("STAT", 40) + offerings("COMPSCI", 500) + offerings("INFO", 30)


def test_a_total_schedule_outage_publishes_nothing(refresh, packaged_catalogs, tmp_path: Path):
    """The whole point: an empty offerings table must never reach a student."""
    target = tmp_path / "data"
    status, stdout, stderr = run_refresh(
        refresh, packaged_catalogs, target, ([], [(TERM, "STAT", "HTTP 503")])
    )

    assert status == 1
    assert stdout == "", "the workflow keys off this; it must not say 'changed'"
    assert "REFUSING TO PUBLISH" in stderr
    assert not (target / "term_offerings.csv").exists()


def test_one_failed_subject_keeps_its_previous_rows_and_says_which(refresh, packaged_catalogs, tmp_path: Path):
    """A failed subject is unknown, not empty. Carrying it forward beats a hole."""
    target = tmp_path / "data"
    seed_previous(target, PREVIOUS)
    fresh = offerings("COMPSCI", 500) + offerings("INFO", 30)

    status, stdout, _ = run_refresh(
        refresh, packaged_catalogs, target, (fresh, [(TERM, "STAT", "HTTP 503")])
    )

    assert status == 0 and stdout == "changed"
    manifest = json.loads((target / "catalog_meta.json").read_text(encoding="utf-8"))
    assert manifest["stale_subjects"] == [f"STAT ({TERM})"]
    assert manifest["offering_count"] == 570

    published = list(csv.DictReader((target / "term_offerings.csv").read_text(encoding="utf-8").splitlines()))
    assert sum(1 for row in published if row["subject"] == "STAT") == 40


def test_a_subject_that_vanished_from_a_working_crawl_blocks_publication(refresh, packaged_catalogs, tmp_path: Path):
    """Nothing failed, yet a whole department lost its courses. That needs a human."""
    target = tmp_path / "data"
    seed_previous(target, PREVIOUS)

    status, stdout, stderr = run_refresh(
        refresh, packaged_catalogs, target, (offerings("COMPSCI", 500) + offerings("INFO", 30), [])
    )

    assert status == 1 and stdout == ""
    assert "STAT" in stderr
    assert "--allow-coverage-loss" in stderr


def test_a_maintainer_can_override_a_genuine_coverage_loss(refresh, packaged_catalogs, tmp_path: Path):
    target = tmp_path / "data"
    seed_previous(target, PREVIOUS)

    status, stdout, stderr = run_refresh(
        refresh, packaged_catalogs, target, (offerings("COMPSCI", 500) + offerings("INFO", 30), []),
        extra_args=("--allow-coverage-loss",),
    )

    assert status == 0 and stdout == "changed"
    assert "overridden by --allow-coverage-loss" in stderr


def test_widespread_failures_block_publication_even_with_carry_forward(refresh, packaged_catalogs, tmp_path: Path):
    target = tmp_path / "data"
    seed_previous(target, PREVIOUS)
    failures = [(TERM, f"SUBJ{n}", "HTTP 503") for n in range(60)]

    status, stdout, stderr = run_refresh(
        refresh, packaged_catalogs, target, (offerings("COMPSCI", 600), failures)
    )

    assert status == 1 and stdout == ""
    assert "over the 10% tolerance" in stderr


def test_a_healthy_first_run_with_no_previous_snapshot_publishes(refresh, packaged_catalogs, tmp_path: Path):
    target = tmp_path / "data"
    status, stdout, _ = run_refresh(refresh, packaged_catalogs, target, (offerings("COMPSCI", 600), []))

    assert status == 0 and stdout == "changed"
    manifest = json.loads((target / "catalog_meta.json").read_text(encoding="utf-8"))
    assert manifest["offering_count"] == 600
    assert "stale_subjects" not in manifest


def test_a_thin_but_unfailed_term_is_still_refused(refresh, packaged_catalogs, tmp_path: Path):
    """No exception was raised, but 12 courses is not a Berkeley semester."""
    target = tmp_path / "data"
    status, stdout, stderr = run_refresh(refresh, packaged_catalogs, target, (offerings("COMPSCI", 12), []))

    assert status == 1 and stdout == ""
    assert "expected at least" in stderr


# -- the helpers, directly -------------------------------------------------------


def test_carry_forward_only_covers_subjects_that_actually_failed(refresh):
    rows = offerings("COMPSCI", 2)
    merged, stale = refresh.carry_forward(rows, PREVIOUS, [(TERM, "STAT", "boom")])
    assert stale == [f"STAT ({TERM})"]
    assert {row["subject"] for row in merged} == {"COMPSCI", "STAT"}
    assert not any(row["subject"] == "INFO" for row in merged), "INFO did not fail; it is not carried"


def test_carry_forward_prefers_fresh_rows_over_stale_ones(refresh):
    """A subject that failed on one term but succeeded on another keeps the fresh rows."""
    rows = offerings("STAT", 3)
    merged, stale = refresh.carry_forward(rows, PREVIOUS, [(TERM, "STAT", "boom")])
    assert stale == []
    assert len(merged) == 3


def test_coverage_problems_is_quiet_when_everything_worked(refresh):
    terms = [schedule.Facet("8588", TERM, 6134)]
    assert refresh.coverage_problems(PREVIOUS, PREVIOUS, terms, [], 240) == []
