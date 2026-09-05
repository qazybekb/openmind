"""The parts of the data-refresh job that can be tested without touching the network."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

from openmind.schedule import Facet

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_the_content_hash_is_stable_and_order_independent(refresh, tmp_path: Path):
    first = tmp_path / "a.csv"
    second = tmp_path / "b.csv"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    digest = refresh.content_hash([first, second])
    assert digest == refresh.content_hash([second, first])

    second.write_text("changed", encoding="utf-8")
    assert digest != refresh.content_hash([first, second])
