"""Tests for verified manifest-driven CMS raw loading into DuckDB."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pytest

from kidney_care_mart.contracts.cms_om_gv import REQUIRED_COLUMNS
from kidney_care_mart.extract.manifest import canonical_json_bytes
from kidney_care_mart.stage import cms_om_gv as stage_module
from kidney_care_mart.stage.cms_om_gv import (
    StageLoadConflictError,
    StageLoadError,
    load_cms_om_gv_snapshot,
)

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "cms_om_gv"
FIXTURE_CSV = FIXTURE_DIR / "staging.csv"
FIXTURE_MANIFEST = FIXTURE_DIR / "staging-manifest.json"


def materialize_fixture_raw_root(tmp_path: Path) -> tuple[Path, Path]:
    """Copy the tracked immutable fixture into a source-shaped raw root."""
    raw_root = tmp_path / "raw"
    manifest_bytes = FIXTURE_MANIFEST.read_bytes()
    payload = json.loads(manifest_bytes)
    blob_path = raw_root.joinpath(*payload["storage"]["blob_path"].split("/"))
    blob_path.parent.mkdir(parents=True)
    blob_path.write_bytes(FIXTURE_CSV.read_bytes())
    manifest_path = (
        raw_root / "manifests" / "cms_om_gv" / f"{payload['pipeline']['run_id']}.json"
    )
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(manifest_bytes)
    return raw_root, manifest_path


def write_manifest_variant(
    raw_root: Path,
    payload: dict[str, object],
    *,
    filename: str,
) -> Path:
    """Write one canonical negative-test manifest beneath the fixture root."""
    path = raw_root / "manifests" / "cms_om_gv" / filename
    path.write_bytes(canonical_json_bytes(payload))
    return path


def test_verified_snapshot_loads_required_values_as_raw_text(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_raw_root(tmp_path)
    database_path = tmp_path / "stage.duckdb"

    result = load_cms_om_gv_snapshot(
        manifest_path=manifest_path,
        raw_root=raw_root,
        database_path=database_path,
    )

    assert result.status == "loaded"
    assert result.row_count == 11
    assert result.database_path == database_path.resolve()
    assert not result.database_noop
    with duckdb.connect(str(database_path), read_only=True) as connection:
        columns = connection.execute("describe select * from raw.cms_om_gv").fetchall()
        types_by_name = {name: data_type for name, data_type, *_ in columns}
        assert all(types_by_name[name] == "VARCHAR" for name in REQUIRED_COLUMNS)
        values = connection.execute(
            """
            select
                "BENE_GEO_LVL",
                "BENE_GEO_CD",
                "BENES_OM_CNT",
                "BENES_OP_DLYS_CNT",
                "BENES_OP_DLYS_PCT"
            from raw.cms_om_gv
            where "BENE_GEO_DESC" in (
                'AL-Synthetic Autauga',
                'AL-Synthetic Barbour',
                'AL-Synthetic Bibb',
                'DC'
            ) and "BENE_AGE_LVL" = 'All'
            order by "BENE_GEO_LVL", "BENE_GEO_CD"
            """
        ).fetchall()
        assert values == [
            ("County", "01001", "1000", "20", "0.0200"),
            ("County", "01005", "", "", ""),
            ("County", "01007", "NA", "NA", "NA"),
            ("State", "11", "0", "0", "0"),
        ]


def test_loaded_rows_retain_one_manifest_lineage(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_raw_root(tmp_path)
    database_path = tmp_path / "stage.duckdb"

    result = load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)

    with duckdb.connect(str(database_path), read_only=True) as connection:
        lineage = connection.execute(
            """
            select distinct
                source_id,
                source_manifest_run_id,
                source_content_sha256,
                source_retrieved_at_utc,
                source_modified_at
            from raw.cms_om_gv
            """
        ).fetchall()
        audit = connection.execute(
            "select row_count, content_sha256 from raw.cms_om_gv_load_audit"
        ).fetchone()
    assert lineage == [
        (
            "cms_om_gv",
            "cms-om-gv-staging-fixture-001",
            result.content_sha256,
            "2026-08-14T12:00:00Z",
            "2026-05-15",
        )
    ]
    assert audit == (11, result.content_sha256)


def test_identical_load_is_an_idempotent_database_noop(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_raw_root(tmp_path)
    database_path = tmp_path / "stage.duckdb"

    first = load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)
    second = load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)

    assert not first.database_noop
    assert second.status == "database_noop"
    assert second.database_noop
    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert connection.execute("select count(*) from raw.cms_om_gv").fetchone() == (
            11,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update({"manifest_format_version": 2}), "format"),
        (
            lambda payload: payload["source"].update(
                {"logical_source_id": "other_source"}
            ),
            "source",
        ),
        (
            lambda payload: payload["schema"].update(
                {"contract_version": "cms_om_gv.raw.v0"}
            ),
            "contract",
        ),
        (
            lambda payload: payload["schema"].update({"schema_sha256": "0" * 64}),
            "schema hash",
        ),
    ],
)
def test_unsupported_or_unreconciled_manifest_cannot_create_database(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    raw_root, _ = materialize_fixture_raw_root(tmp_path)
    payload = json.loads(FIXTURE_MANIFEST.read_bytes())
    mutation(payload)
    manifest_path = write_manifest_variant(raw_root, payload, filename="invalid.json")
    database_path = tmp_path / "stage.duckdb"

    with pytest.raises(StageLoadError, match=message):
        load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)

    assert not database_path.exists()


def test_manifest_blob_path_cannot_escape_raw_root(tmp_path: Path) -> None:
    raw_root, _ = materialize_fixture_raw_root(tmp_path)
    payload = json.loads(FIXTURE_MANIFEST.read_bytes())
    payload["storage"]["blob_path"] = "../outside.csv"
    manifest_path = write_manifest_variant(raw_root, payload, filename="escape.json")

    with pytest.raises(StageLoadError, match="blob path"):
        load_cms_om_gv_snapshot(manifest_path, raw_root, tmp_path / "stage.duckdb")

    assert not (tmp_path / "stage.duckdb").exists()


def test_corrupt_blob_cannot_create_database(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_raw_root(tmp_path)
    payload = json.loads(FIXTURE_MANIFEST.read_bytes())
    blob_path = raw_root.joinpath(*payload["storage"]["blob_path"].split("/"))
    blob_path.write_bytes(b"corrupt")

    with pytest.raises(StageLoadError, match="integrity"):
        load_cms_om_gv_snapshot(manifest_path, raw_root, tmp_path / "stage.duckdb")

    assert not (tmp_path / "stage.duckdb").exists()


def test_preexisting_partial_database_is_not_overwritten(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_raw_root(tmp_path)
    database_path = tmp_path / "missing-parent" / "stage.duckdb"
    database_path.parent.mkdir()
    temporary_path = database_path.with_name(
        ".stage.duckdb.cms-om-gv-staging-fixture-001.partial"
    )
    temporary_path.write_bytes(b"occupied")

    with pytest.raises(StageLoadConflictError, match="staging path"):
        load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)

    assert not database_path.exists()
    assert temporary_path.read_bytes() == b"occupied"


def test_loader_failure_cleans_its_partial_database_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_root, manifest_path = materialize_fixture_raw_root(tmp_path)
    database_path = tmp_path / "stage.duckdb"
    temporary_path = database_path.with_name(
        ".stage.duckdb.cms-om-gv-staging-fixture-001.partial"
    )
    wal_path = Path(f"{temporary_path}.wal")

    def fail_after_creating_partials(*_args) -> None:
        temporary_path.write_bytes(b"partial")
        wal_path.write_bytes(b"partial wal")
        raise OSError("fixture write failure")

    monkeypatch.setattr(stage_module, "_load_database", fail_after_creating_partials)

    with pytest.raises(StageLoadError, match="raw load failed"):
        load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)

    assert not database_path.exists()
    assert not temporary_path.exists()
    assert not wal_path.exists()


def test_different_manifest_cannot_overwrite_existing_database(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_raw_root(tmp_path)
    database_path = tmp_path / "stage.duckdb"
    load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)
    original_bytes = database_path.read_bytes()
    payload = json.loads(FIXTURE_MANIFEST.read_bytes())
    payload["pipeline"]["run_id"] = "cms-om-gv-staging-fixture-002"
    other_manifest = write_manifest_variant(
        raw_root,
        payload,
        filename="cms-om-gv-staging-fixture-002.json",
    )

    with pytest.raises(StageLoadConflictError, match="different manifest"):
        load_cms_om_gv_snapshot(other_manifest, raw_root, database_path)

    assert database_path.read_bytes() == original_bytes
