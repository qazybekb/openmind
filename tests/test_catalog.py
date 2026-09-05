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
    assert result["courses"][0]["offered_terms"][0]["instructors"] == "Peng Ding"


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
    assert len(preview) == catalog.DESCRIPTION_PREVIEW
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
