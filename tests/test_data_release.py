"""A locally refreshed snapshot must be publishable without another crawl."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from openmind import catalog
from scripts.prepare_data_release import prepare
from tests.test_catalog import stub_http

ROOT = Path(__file__).resolve().parents[1]


def test_preparing_an_unpublished_snapshot_fills_its_hash(sample_catalog, tmp_path):
    manifest_path = sample_catalog / "catalog_meta.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["data_sha256"] = ""
    manifest_path.write_text(json.dumps(manifest))
    result = prepare(sample_catalog, tmp_path / "assets")
    manifest = json.loads(manifest_path.read_text())
    assert manifest["data_sha256"] == hashlib.sha256(Path(result["file"]).read_bytes()).hexdigest()
    assert result["tag"] in manifest["asset_url"]


def test_preparation_is_byte_identical_after_the_hash_is_written(sample_catalog, tmp_path):
    first = prepare(sample_catalog, tmp_path / "first")
    manifest_before = (sample_catalog / "catalog_meta.json").read_bytes()
    second = prepare(sample_catalog, tmp_path / "second")
    assert first["tag"] == second["tag"] and first["sha"] == second["sha"]
    assert Path(first["file"]).read_bytes() == Path(second["file"]).read_bytes()
    assert (sample_catalog / "catalog_meta.json").read_bytes() == manifest_before


def test_a_same_day_correction_gets_an_immutable_asset_identity(sample_catalog, tmp_path):
    first = prepare(sample_catalog, tmp_path / "first")
    target = sample_catalog / "term_offerings.csv"
    target.write_bytes(target.read_bytes().replace(b"Peng Ding", b"New Instructor"))
    second = prepare(sample_catalog, tmp_path / "second")
    assert first["date"] == second["date"]
    assert first["tag"] != second["tag"] and first["sha"] != second["sha"]


def test_manifest_key_order_cannot_change_an_immutable_asset(sample_catalog, tmp_path):
    first = prepare(sample_catalog, tmp_path / "first")
    target = sample_catalog / "catalog_meta.json"
    manifest = json.loads(target.read_text())
    target.write_text(json.dumps(dict(reversed(list(manifest.items())))))
    second = prepare(sample_catalog, tmp_path / "second")
    assert first["tag"] == second["tag"] and first["sha"] == second["sha"]


def test_the_prepared_asset_reaches_an_existing_client(sample_catalog, tmp_path, monkeypatch):
    result = prepare(sample_catalog, tmp_path / "assets")
    manifest = json.loads((sample_catalog / "catalog_meta.json").read_text())
    calls = []
    stub_http(monkeypatch, manifest, Path(result["file"]).read_bytes(), calls)
    assert catalog.maybe_update(enabled=True, force=True)
    with catalog.connect() as conn:
        assert catalog.meta(conn)["data_sha256"] == result["sha"]
        assert catalog.details(conn, "STAT", "156")
    assert catalog.maybe_update(enabled=True, force=True) is None
    assert len(calls) == 3


def test_publication_does_not_depend_on_a_crawl_changing_data():
    workflow = (ROOT / ".github/workflows/refresh-data.yml").read_text()
    assert "publish_only:" in workflow
    assert "github.repository == 'qazybekb/openmind'" in workflow
    assert "steps.refresh.outputs.status" not in workflow
    assert workflow.index("Publish and verify the immutable asset") < workflow.index("git add src/openmind/data")
    assert "--clobber" not in workflow
    assert "test \"$VERIFIED\" = \"sha256:$SHA\"" in workflow
