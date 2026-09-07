"""The Berkeley catalog index, its provenance stamps, and the public data update."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from openmind import catalog

# -- the shipped snapshot ------------------------------------------------------


@pytest.fixture(scope="module")
def packaged(tmp_path_factory) -> Path:
    """Build the catalog from the data actually shipped in the wheel. Built once."""
    target = tmp_path_factory.mktemp("catalog") / "catalog.db"
    catalog.build(target)
    return target


def test_the_shipped_catalog_covers_the_whole_university(packaged: Path):
    """Floors, not exact counts: the data refreshes on its own cadence."""
    with catalog.connect(packaged) as conn:
        courses = conn.execute("SELECT COUNT(*) FROM catalog_courses").fetchone()[0]
        subjects = len(catalog.subjects(conn))
    assert courses >= catalog.MIN_COURSES
    assert subjects >= catalog.MIN_SUBJECTS


def test_the_shipped_snapshot_is_not_a_year_stale(packaged: Path):
    """Advice from an unmaintained catalog should fail CI, not mislead a student."""
    with catalog.connect(packaged) as conn:
        as_of = catalog.meta(conn).get("catalog_as_of", "")
    captured = date.fromisoformat(as_of)
    assert date.today() - captured < timedelta(days=365), f"catalog snapshot {as_of} is over a year old"


def test_both_levels_are_present(packaged: Path):
    with catalog.connect(packaged) as conn:
        levels = {row[0] for row in conn.execute("SELECT DISTINCT level FROM catalog_courses")}
    assert levels == {"undergraduate", "graduate"}


def test_a_real_course_can_be_looked_up(packaged: Path):
    with catalog.connect(packaged) as conn:
        course = catalog.details(conn, "COMPSCI", "189")
    assert course is not None
    assert "Machine Learning" in course["title"]
    assert course["units"] == "4"


def test_a_cross_listed_course_is_found_without_its_c(packaged: Path):
    """"STAT 205A" is catalogued as "STAT C205A"; the C must not hide it."""
    with catalog.connect(packaged) as conn:
        course = catalog.details(conn, "STAT", "205A")
        exact = catalog.details(conn, "STAT", "C205A")
    assert course is not None and exact is not None
    assert course["number"] == exact["number"] == "C205A"


# -- search --------------------------------------------------------------------


def test_keyword_search_ranks_titles_above_descriptions(sample_catalog):
    with catalog.connect() as conn:
        result = catalog.search(conn, query="causal inference")
    assert result["courses"][0]["number"] == "156"
    assert result["catalog_as_of"] == "2026-09-05"
    assert result["terms_known"] == ["Fall 2026"]


def test_a_course_code_is_matched_as_a_code_not_as_two_words(sample_catalog):
    with catalog.connect() as conn:
        for query in ("STAT 156", "stat156", "STAT-156"):
            result = catalog.search(conn, query=query)
            assert [(c["subject"], c["number"]) for c in result["courses"]] == [("STAT", "156")], query


def test_filters_narrow_the_result_set(sample_catalog):
    with catalog.connect() as conn:
        assert catalog.search(conn, subject="INFO")["total"] == 1
        assert catalog.search(conn, level="graduate")["total"] == 1
        assert catalog.search(conn, units="4")["total"] == 3
        assert catalog.search(conn, subject="NOPE")["total"] == 0


def test_the_offered_term_filter_keeps_only_scheduled_courses(sample_catalog):
    with catalog.connect() as conn:
        result = catalog.search(conn, offered_term="Fall 2026", limit=30)
    assert [(c["subject"], c["number"]) for c in result["courses"]] == [("STAT", "156")]
    assert result["courses"][0]["offered_terms"][0] == {"term": "Fall 2026", "sections": 1}


def test_a_course_missing_from_the_printed_catalog_is_flagged(sample_catalog):
    """STAT 156 is hidden by the catalog's default filters but is really offered."""
    with catalog.connect() as conn:
        stat = catalog.details(conn, "STAT", "156")
        compsci = catalog.details(conn, "COMPSCI", "189")
    assert stat["in_printed_catalog"] is False
    assert "in_printed_catalog" not in compsci


def test_descriptions_are_previewed_in_search_and_full_in_detail(sample_catalog):
    with catalog.connect() as conn:
        conn.execute("UPDATE catalog_courses SET description = ? WHERE subject = 'COMPSCI'", ("x" * 600,))
        conn.commit()
        preview = catalog.search(conn, subject="COMPSCI")["courses"][0]["description"]
        full = catalog.details(conn, "COMPSCI", "189")["description"]
    assert len(preview) <= catalog.SEARCH_PREVIEW
    assert preview.endswith("...")
    assert len(full) == 600


def test_the_result_limit_is_capped(sample_catalog):
    with catalog.connect() as conn:
        assert len(catalog.search(conn, query="", limit=999)["courses"]) <= catalog.MAX_LIMIT


@pytest.mark.parametrize("query", ['NEAR("a" "b")', "machine*", 'x" OR "y', "((("])
def test_fts_operators_in_a_catalog_query_are_literal_words(query: str, sample_catalog):
    with catalog.connect() as conn:
        catalog.search(conn, query=query)  # must not raise


@pytest.mark.parametrize(
    ("code", "expected"),
    [("STAT 156", ("STAT", "156")), ("compsci 61a", ("COMPSCI", "61A")), ("INFO-259", ("INFO", "259")),
     ("STAT156", ("STAT", "156")), ("nonsense", None), ("", None), ("156", None)],
)
def test_course_codes_are_parsed_forgivingly(code: str, expected):
    assert catalog.parse_course_code(code) == expected


# -- data updates --------------------------------------------------------------


def make_asset(source: Path) -> tuple[bytes, str]:
    """Pack a data snapshot the way the refresh job publishes it."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for name in ("undergraduate_courses.csv", "graduate_courses.csv", "term_offerings.csv",
                     "catalog_meta.json"):
            archive.add(source / name, arcname=f"data/{name}")
    body = buffer.getvalue()
    return body, hashlib.sha256(body).hexdigest()


def stub_http(monkeypatch: pytest.MonkeyPatch, manifest: dict, asset: bytes | None, calls: list[str]):
    """Serve the manifest and asset over a mock transport, recording every request."""
    def responder(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("catalog_meta.json"):
            return httpx.Response(200, json=manifest, request=request)
        if asset is None:
            return httpx.Response(404, request=request)
        return httpx.Response(200, content=asset, request=request)

    transport = httpx.MockTransport(responder)
    real_get, real_stream = httpx.get, httpx.stream

    def fake_get(url, **kwargs):
        kwargs.pop("follow_redirects", None)
        with httpx.Client(transport=transport) as client:
            return client.get(url, **{k: v for k, v in kwargs.items() if k != "timeout"})

    class FakeStream:
        def __init__(self, method, url, **kwargs):
            self.client = httpx.Client(transport=transport)
            self.method, self.url = method, url

        def __enter__(self):
            self.response = self.client.request(self.method, self.url)
            return self.response

        def __exit__(self, *exc):
            self.client.close()

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "stream", FakeStream)
    return real_get, real_stream


def test_an_update_is_skipped_when_the_hash_already_matches(sample_catalog, monkeypatch):
    calls: list[str] = []
    stub_http(monkeypatch, {"catalog_as_of": "2026-09-05", "data_sha256": "0" * 64}, None, calls)
    assert catalog.maybe_update(enabled=True, force=True) is None
    assert len(calls) == 1, "the manifest is fetched; the asset is not"


def test_a_newer_snapshot_is_downloaded_verified_and_rebuilt(sample_catalog, monkeypatch, home):
    asset, digest = make_asset(sample_catalog)
    calls: list[str] = []
    stub_http(monkeypatch, {
        "catalog_as_of": "2026-10-01", "data_sha256": digest,
        "asset_url": "https://example.invalid/catalog-2026-10-01.tar.gz",
    }, asset, calls)

    message = catalog.maybe_update(enabled=True, force=True)
    assert message is not None and "2026-10-01" in message
    with catalog.connect() as conn:
        assert catalog.meta(conn)["data_sha256"] == digest


@pytest.mark.parametrize("force", [False, True])
def test_a_same_day_correction_is_downloaded_once(sample_catalog, monkeypatch, force):
    asset, digest = make_asset(sample_catalog)
    calls = []
    stub_http(monkeypatch, {"catalog_as_of": "2026-09-05", "data_sha256": digest}, asset, calls)
    assert catalog.maybe_update(enabled=True, force=force)
    assert len(calls) == 2
    assert catalog.maybe_update(enabled=True, force=True) is None
    assert len(calls) == 3
    with catalog.connect() as conn:
        assert catalog.meta(conn)["data_sha256"] == digest


def test_an_older_snapshot_cannot_roll_back_a_client(sample_catalog, monkeypatch):
    asset, digest = make_asset(sample_catalog)
    calls = []
    stub_http(monkeypatch, {"catalog_as_of": "2026-09-04", "data_sha256": digest}, asset, calls)
    assert catalog.maybe_update(enabled=True, force=True) is None
    assert len(calls) == 1


def test_a_corrupted_asset_is_rejected_and_the_old_catalog_survives(sample_catalog, monkeypatch):
    asset, _ = make_asset(sample_catalog)
    calls: list[str] = []
    stub_http(monkeypatch, {
        "catalog_as_of": "2026-10-01", "data_sha256": "f" * 64,
        "asset_url": "https://example.invalid/bad.tar.gz",
    }, asset, calls)

    assert catalog.maybe_update(enabled=True, force=True) is None
    with catalog.connect() as conn:
        assert catalog.meta(conn)["catalog_as_of"] == "2026-09-05"
        assert conn.execute("SELECT COUNT(*) FROM catalog_courses").fetchone()[0] == 3


def test_turning_updates_off_makes_no_request_at_all(sample_catalog, monkeypatch):
    calls: list[str] = []
    stub_http(monkeypatch, {"catalog_as_of": "2026-12-01", "data_sha256": "a" * 64}, None, calls)
    assert catalog.maybe_update(enabled=False, force=True) is None
    assert calls == []


def test_the_check_happens_at_most_once_a_day(sample_catalog, monkeypatch, home):
    calls: list[str] = []
    stub_http(monkeypatch, {"catalog_as_of": "2026-09-05", "data_sha256": "0" * 64}, None, calls)

    catalog.maybe_update(enabled=True)
    assert len(calls) == 1
    catalog.maybe_update(enabled=True)
    assert len(calls) == 1, "a second call the same day must not hit the network"

    stale = datetime.now(UTC) - timedelta(days=2)
    (home / "data_check").write_text(str(stale.timestamp()), encoding="utf-8")
    catalog.maybe_update(enabled=True)
    assert len(calls) == 2


def test_a_network_failure_during_an_update_is_survivable(sample_catalog, monkeypatch):
    def dead(url, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", dead)
    assert catalog.maybe_update(enabled=True, force=True) is None
    with catalog.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM catalog_courses").fetchone()[0] == 3


def test_an_asset_containing_a_path_traversal_member_writes_nothing_outside(tmp_path: Path, sample_catalog):
    """An archive is untrusted input like any other download."""
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        payload = b"pwned"
        info = tarfile.TarInfo("../../../../tmp/openmind-escape.csv")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    destination = tmp_path / "staging"
    catalog._extract_asset(buffer.getvalue(), destination)
    assert not Path("/tmp/openmind-escape.csv").exists()
    assert list(destination.iterdir()) == []


def test_the_catalog_reports_a_missing_index_with_the_command_to_fix_it(home: Path):
    with pytest.raises(catalog.CatalogError, match="openmind setup"), catalog.connect():
        pass


def test_meta_json_is_read_from_the_data_snapshot(sample_catalog):
    with catalog.connect() as conn:
        info = catalog.meta(conn)
    assert info["catalog_as_of"] == "2026-09-05"
    assert json.loads(info["terms_known"]) == ["Fall 2026"]


NOT_REFRESHED = "offerings not refreshed: classes.berkeley.edu returned HTTP 403; previous snapshot kept"


def test_a_snapshot_that_kept_its_previous_offerings_says_so(sample_catalog: Path):
    """An offerings date older than the catalog date, read alone, looks like "not offered"."""
    path = sample_catalog / "catalog_meta.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**meta, "offerings_note": NOT_REFRESHED}), encoding="utf-8")
    catalog.build(source_dir=sample_catalog)

    with catalog.connect() as conn:
        assert catalog.offerings_note(conn) == NOT_REFRESHED
        assert catalog.search(conn, query="causal inference")["offerings_note"] == NOT_REFRESHED


def test_a_snapshot_with_freshly_crawled_offerings_carries_no_note(sample_catalog):
    """The note is the exception; a normal snapshot must not add a line saying nothing."""
    with catalog.connect() as conn:
        assert catalog.offerings_note(conn) == ""
        assert "offerings_note" not in catalog.search(conn, query="causal inference")


# -- ranking and budget --------------------------------------------------------


def test_a_course_titled_after_the_query_outranks_one_that_merely_mentions_it(packaged: Path):
    """bm25 alone buried STAT 156 "Causal Inference" below courses whose descriptions repeat the words."""
    with catalog.connect(packaged) as conn:
        result = catalog.search(conn, query="causal inference", limit=10)

    top_three = [(c["subject"], c["number"]) for c in result["courses"][:3]]
    assert ("STAT", "156") in top_three, top_three
    assert ("STAT", "256") in top_three, top_three
    assert result["total"] > 10, "the query still matches many courses"


def test_titles_containing_the_phrase_come_before_descriptions_that_mention_it(packaged: Path):
    """No Berkeley course is titled exactly "Machine Learning", so the phrase tier decides."""
    with catalog.connect(packaged) as conn:
        titles = [c["title"].lower() for c in catalog.search(conn, query="machine learning", limit=10)["courses"]]
    assert all("machine learning" in title for title in titles[:4]), titles[:4]


def test_the_offering_and_catalog_flags_survive_the_new_ranking(packaged: Path):
    with catalog.connect(packaged) as conn:
        result = catalog.search(conn, query="causal inference", limit=10)
    stat156 = next(c for c in result["courses"] if (c["subject"], c["number"]) == ("STAT", "156"))
    assert stat156["in_printed_catalog"] is False
    assert stat156["offered_terms"][0]["term"] == "Fall 2026"


@pytest.mark.parametrize("query", ['NEAR("a" "b")', "machine*", 'x" OR "y', "100% pure", "a_b"])
def test_ranking_patterns_cannot_inject_operators_or_wildcards(query: str, packaged: Path):
    """The title ranking uses LIKE, so % and _ in a query must be escaped, not matched."""
    with catalog.connect(packaged) as conn:
        catalog.search(conn, query=query, limit=5)  # must not raise
    exact, phrase = catalog._title_rank_patterns("100% a_b")
    assert exact == "100% a_b"
    assert phrase == r"%100\% a\_b%"


def test_a_full_page_of_results_fits_the_tool_budget(packaged: Path):
    """Ten results used to be trimmed to six by `shrink`, silently losing the tail."""
    from openmind import service
    from openmind.service import BUDGETS

    envelope = {
        "as_of": "2026-09-05T10:00:00-07:00", "tz": "America/Los_Angeles",
        "partial": False, "warnings": [],
        "advice_note": "These are fit-based matches from a catalog snapshot, not official advising. "
                       "Prefer courses with known offerings, and check requirements with your advisor.",
    }
    queries = ["causal inference", "machine learning", "data science ethics", "public health policy",
               "research methods", "comparative literature", ""]

    with catalog.connect(packaged) as conn:
        for query in queries:
            payload = catalog.fit_previews(
                {**catalog.search(conn, query=query, limit=10), **envelope}, BUDGETS["search_catalog"]
            )
            # A query with fewer than ten distinct courses returns fewer; what must not
            # happen is the budget silently dropping any of the ones it found.
            assert len(payload["courses"]) == min(10, payload["total"]), query
            # Measured the way the tool serialises it, which is what the budget describes.
            size = service.encoded_size(payload)
            assert size <= BUDGETS["search_catalog"], f"{query!r} produced {size} bytes"


def test_gists_are_shortened_before_whole_courses_are_dropped(packaged: Path):
    """Losing twenty characters of every description beats losing the tenth course."""
    with catalog.connect(packaged) as conn:
        full = catalog.search(conn, query="research methods", limit=10)
    before = [len(str(c.get("description") or "")) for c in full["courses"]]
    assert len(full["courses"]) == 10, "the fixture query must fill a page"

    fitted = catalog.fit_previews(json.loads(json.dumps(full)), 2_500)
    after = [len(str(c.get("description") or "")) for c in fitted["courses"]]

    assert len(fitted["courses"]) == 10, "no course was dropped"
    assert sum(after) < sum(before), "descriptions were shortened"
    # The floor is approximate — `_trim` backs up to a word boundary — but no gist is
    # cut down to something useless.
    assert all(length >= 40 for length in after if length), after


def test_fit_previews_gives_up_rather_than_looping_on_an_impossible_budget(packaged: Path):
    with catalog.connect(packaged) as conn:
        payload = catalog.search(conn, query="statistics", limit=10)
    fitted = catalog.fit_previews(payload, 10)  # unreachable; must terminate
    assert len(fitted["courses"]) == 10


def test_search_previews_leave_the_detail_fields_to_the_detail_tool(packaged: Path):
    """Cross-listings and instructor names are lookup detail, not scanning detail."""
    with catalog.connect(packaged) as conn:
        listed = catalog.search(conn, query="causal inference", limit=10)["courses"]
        detail = catalog.details(conn, "STAT", "156")

    assert all("cross_listed" not in course for course in listed)
    assert all("instructors" not in term for c in listed for term in c.get("offered_terms", []))
    assert detail["offered_terms"][0]["instructors"] == "Peng Ding"


# -- lazy build ----------------------------------------------------------------


def test_the_catalog_builds_itself_on_first_use_without_any_setup(home: Path):
    """Searching public data must not require a Canvas token, or setup, or a rebuild flag."""
    from openmind.config import catalog_db_path

    assert not catalog_db_path().exists()
    built = catalog.ensure_built()
    assert built is not None and built["courses"] >= catalog.MIN_COURSES
    assert catalog_db_path().exists()

    with catalog.connect() as conn:
        assert catalog.search(conn, query="causal inference")["courses"]


def test_a_second_call_does_not_rebuild(home: Path):
    assert catalog.ensure_built() is not None
    assert catalog.ensure_built() is None


# -- cross-listings ---------------------------------------------------------------


def test_one_course_under_three_codes_is_one_result(packaged: Path):
    """DATA C204, STS C204, and HISTORY C254 are the same class filling three of ten slots."""
    with catalog.connect(packaged) as conn:
        result = catalog.search(conn, query="data science ethics", limit=10)

    ethics = [c for c in result["courses"] if c["title"] == "Human Contexts and Ethics of Data"]
    assert len(ethics) == 1
    assert (ethics[0]["subject"], ethics[0]["number"]) == ("DATA", "C204")
    assert ethics[0]["also_listed_as"] == ["HISTORY C254", "STS C204"]


def test_the_subject_filter_decides_which_code_is_shown(packaged: Path):
    """A student who asked for STS should see the STS code, not the alphabetical one."""
    with catalog.connect(packaged) as conn:
        result = catalog.search(conn, query="data science ethics", subject="STS", limit=10)

    primary = result["courses"][0]
    assert (primary["subject"], primary["number"]) == ("STS", "C204")
    assert primary["also_listed_as"] == ["DATA C204", "HISTORY C254"]


def test_without_a_subject_filter_the_alphabetically_first_code_wins(packaged: Path):
    """Stable across runs, and independent of which member the ranking surfaced."""
    with catalog.connect(packaged) as conn:
        for _ in range(3):
            first = catalog.search(conn, query="data science ethics", limit=10)["courses"][0]
            assert (first["subject"], first["number"]) == ("DATA", "C204")


def test_the_total_counts_courses_not_listings(packaged: Path):
    with catalog.connect(packaged) as conn:
        result = catalog.search(conn, query="data science ethics", limit=30)
        rows = conn.execute(
            "SELECT COUNT(*) FROM catalog_fts JOIN catalog_courses c ON c.rowid = catalog_fts.rowid "
            "WHERE catalog_fts MATCH ?",
            [catalog._match_expression("data science ethics", "AND")],
        ).fetchone()[0]

    assert result["total"] < rows, "collapsing must reduce the count, not just the page"
    assert result["total"] == len(result["courses"])


def test_a_course_with_no_cross_listings_says_nothing_about_them(packaged: Path):
    with catalog.connect(packaged) as conn:
        course = catalog.search(conn, query="STAT 156")["courses"][0]
    assert "also_listed_as" not in course


def test_the_detail_tool_still_answers_for_every_code(packaged: Path):
    """Collapsing is a search-result concern; get_catalog_course is unchanged."""
    with catalog.connect(packaged) as conn:
        for subject, number in [("DATA", "C204"), ("STS", "C204"), ("HISTORY", "C254")]:
            course = catalog.details(conn, subject, number)
            assert course is not None
            assert course["title"] == "Human Contexts and Ethics of Data"
            assert course["subject"] == subject


def test_identically_titled_courses_are_ordered_by_code_not_relevance(packaged: Path):
    """STAT 156 and STAT 256 are both "Causal Inference"; bm25 between them is noise."""
    with catalog.connect(packaged) as conn:
        for _ in range(3):
            top = [(c["subject"], c["number"]) for c in
                   catalog.search(conn, query="causal inference", limit=10)["courses"][:2]]
            assert top == [("STAT", "156"), ("STAT", "256")], top


def test_the_stat_156_acceptance_case_still_holds(packaged: Path):
    with catalog.connect(packaged) as conn:
        result = catalog.search(conn, query="causal inference", limit=10)

    codes = [(c["subject"], c["number"]) for c in result["courses"][:3]]
    assert ("STAT", "156") in codes
    stat156 = next(c for c in result["courses"] if (c["subject"], c["number"]) == ("STAT", "156"))
    assert stat156["in_printed_catalog"] is False
    assert stat156["offered_terms"][0]["term"] == "Fall 2026"
    assert len(result["courses"]) == 10


# -- parsing the cross-listing column ---------------------------------------------


SUBJECTS = {"DATA", "HISTORY", "STS", "HISTART", "CIVENG", "MECENG", "POLECON", "MEDIAST", "L & S"}


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("DATAC204 ETHICS OF DATA, HISTORYC254 ETHICS OF DATA", [("DATA", "C204"), ("HISTORY", "C254")]),
        ("CIVENGC30 INTRO SOLID MECHNCS", [("CIVENG", "C30")]),
        # HISTART, not HISTARTC — the longest subject that leaves a usable number wins.
        ("HISTARTC196W SPECIAL RESEARCH", [("HISTART", "C196W")]),
        ("", []),
        ("-", []),
        ("NOTASUBJECT101 SOMETHING", []),
    ],
)
def test_cross_listing_codes_are_split_on_the_subject_not_the_first_digit(cell, expected):
    assert catalog.parse_cross_listed(cell, SUBJECTS) == expected


def test_groups_join_codes_named_in_only_one_direction():
    """The catalog data is asymmetric in places; edges are followed both ways."""
    rows = [
        ("DATA", "C204", "graduate", "Ethics", "4", "4", "Data", "", "HISTORYC254 ETHICS", "", "", 1),
        ("HISTORY", "C254", "graduate", "Ethics", "4", "4", "History", "", "", "", "", 1),
        ("STAT", "156", "undergraduate", "Causal", "4", "4", "Stat", "", "", "", "", 1),
    ]
    groups = catalog.build_groups(rows)

    assert groups[("DATA", "C204")] == groups[("HISTORY", "C254")] == "DATA C204"
    assert groups[("STAT", "156")] == "STAT 156", "a course with no partners is its own group"


def test_a_cross_listing_to_a_course_we_do_not_have_is_ignored():
    rows = [("DATA", "C204", "graduate", "Ethics", "4", "4", "Data", "", "GONEC999 MISSING", "", "", 1)]
    assert catalog.build_groups(rows) == {("DATA", "C204"): "DATA C204"}


# -- rebuilding on a schema change -------------------------------------------------


def test_an_index_built_by_an_older_version_is_rebuilt(home: Path, sample_catalog):
    """group_key did not exist before; querying an old index would fail on the column."""
    from openmind.config import catalog_db_path

    with catalog.connect(catalog_db_path()) as conn:
        conn.execute("UPDATE meta SET value = '1' WHERE key = 'schema_version'")
        conn.commit()

    assert catalog.ensure_built() is not None, "the stale index should have been rebuilt"

    with catalog.connect() as conn:
        assert catalog.meta(conn)["schema_version"] == catalog.SCHEMA_VERSION


# -- sizing the overfetch from the data -------------------------------------------


def test_the_largest_group_in_the_data_is_recorded(packaged: Path):
    with catalog.connect(packaged) as conn:
        recorded = int(catalog.meta(conn)["max_group_size"])
        actual = conn.execute(
            "SELECT MAX(n) FROM (SELECT COUNT(*) AS n FROM catalog_courses GROUP BY group_key)"
        ).fetchone()[0]

    assert recorded == actual
    assert recorded >= 8, "the packaged catalog contains groups of eight codes"


def test_the_overfetch_never_drops_below_its_floor(packaged: Path):
    with catalog.connect(packaged) as conn:
        assert catalog.overfetch(conn) == max(int(catalog.meta(conn)["max_group_size"]), catalog._MIN_OVERFETCH)
        conn.execute("UPDATE meta SET value = '2' WHERE key = 'max_group_size'")
        conn.commit()
        assert catalog.overfetch(conn) == catalog._MIN_OVERFETCH


def test_an_index_with_no_recorded_group_size_still_works(packaged: Path):
    with catalog.connect(packaged) as conn:
        conn.execute("DELETE FROM meta WHERE key = 'max_group_size'")
        conn.commit()
        assert catalog.overfetch(conn) == catalog._MIN_OVERFETCH


def test_a_page_is_not_cut_short_by_one_very_large_cross_listing_group(home: Path, tmp_path: Path):
    """Nine codes for one course used to eat the whole over-fetch window."""
    import csv

    source = tmp_path / "big-group"
    source.mkdir()
    codes = [f"SUBJ{n}" for n in range(9)]
    fields = ["Subject", "Course Number", "Department(s)", "Course Title",
              "Credits - Units - Minimum Units", "Credits - Units - Maximum Units", "Terms Offered",
              "Course Description", "Cross-Listed Course(s)", "Repeat Rules",
              "Repeat Rule: Special Circumstances", "Offering Information", "Additional Offering Information"]

    def row(subject: str, number: str, title: str, cross: str) -> dict[str, str]:
        return {**dict.fromkeys(fields, "-"), "Subject": subject, "Course Number": number,
                "Course Title": title, "Course Description": "Shared seminar on research methods.",
                "Credits - Units - Minimum Units": "4", "Credits - Units - Maximum Units": "4",
                "Cross-Listed Course(s)": cross, "Department(s)": "Somewhere"}

    rows = [
        row(code, "C196", "Shared Seminar",
            ", ".join(f"{other}C196 SHARED SEMINAR" for other in codes if other != code))
        for code in codes
    ]
    # Ten unrelated courses that also match, so a full page is available.
    rows += [row(f"OTHER{n}", "101", f"Research Methods {n}", "-") for n in range(10)]

    for name in ("undergraduate_courses.csv", "graduate_courses.csv"):
        with (source / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows if name.startswith("under") else [])

    catalog.build(source_dir=source)

    with catalog.connect() as conn:
        assert int(catalog.meta(conn)["max_group_size"]) == 9
        result = catalog.search(conn, query="research methods seminar", limit=10)

    assert result["total"] == 11, "nine codes plus ten others collapse to eleven courses"
    assert len(result["courses"]) == 10, "a page of ten was available and must be returned"
    keys = [(c["subject"], c["number"]) for c in result["courses"]]
    assert len(keys) == len(set(keys))
