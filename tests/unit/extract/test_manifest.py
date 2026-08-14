"""Tests for raw CSV evidence, canonical manifests, and immutable publication."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from kidney_care_mart.contracts.cms_om_gv import (
    CONTRACT_VERSION,
    GRAIN_KEYS,
    REQUIRED_COLUMNS,
    ColumnSchema,
)
from kidney_care_mart.extract.manifest import (
    BlobIntegrityError,
    CsvValidationError,
    ManifestConflictError,
    ManifestReconciliationError,
    SnapshotManifest,
    canonical_json_bytes,
    canonical_json_sha256,
    header_sha256,
    publish_snapshot,
    reconcile_manifest_file,
    schema_sha256,
    validate_raw_csv,
    validate_run_id,
)

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "cms_om_gv" / "download.csv"


def fixture_header() -> tuple[str, ...]:
    """Return the fixture header without typing or normalization."""
    with FIXTURE_PATH.open(encoding="utf-8", newline="") as fixture:
        return tuple(next(csv.reader(fixture)))


def fixture_schema() -> tuple[ColumnSchema, ...]:
    """Return official-shaped declared types in exact fixture order."""
    return tuple(
        ColumnSchema(
            name=name,
            declared_type=REQUIRED_COLUMNS.get(name, "TEXT"),
        )
        for name in fixture_header()
    )


def copy_fixture(destination: Path) -> bytes:
    """Copy fixture bytes to a staged path and return them."""
    content = FIXTURE_PATH.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    return content


def valid_manifest(
    staged_path: Path,
    *,
    run_id: str = "cms-om-gv-fixture-001",
) -> SnapshotManifest:
    """Build a manifest that exactly describes a staged fixture."""
    content = staged_path.read_bytes()
    evidence = validate_raw_csv(
        staged_path,
        fixture_schema(),
        expected_row_count=2,
    )
    content_hash = hashlib.sha256(content).hexdigest()
    return SnapshotManifest(
        manifest_format_version=1,
        logical_source_id="cms_om_gv",
        pipeline_run_id=run_id,
        extractor_version="0.1.0",
        contract_version=CONTRACT_VERSION,
        official_catalog_url="https://data.cms.gov/data.json",
        official_landing_url=(
            "https://data.cms.gov/summary-statistics-on-use-and-payments/"
            "medicare-geographic-comparisons/"
            "medicare-geographic-variation-by-national-state-county"
        ),
        stable_dataset_id="6219697b-8f6c-4164-bed4-cd9317c58ebc",
        resolved_csv_url="https://data.cms.gov/sites/default/files/current/file.csv",
        retrieved_at_utc="2026-08-14T12:00:00Z",
        source_release="2014-01-01/2024-12-31",
        source_modified_date="2026-05-15",
        http_etag='"fixture-etag"',
        http_last_modified="Fri, 14 Aug 2026 12:00:00 GMT",
        content_sha256=content_hash,
        byte_count=len(content),
        csv_row_count=evidence.row_count,
        transport_mode="full_csv",
        page_count=1,
        record_count=evidence.row_count,
        columns=fixture_schema(),
        schema_sha256=schema_sha256(fixture_schema()),
        header_sha256=evidence.header_sha256,
        additive_columns=evidence.additive_columns,
        blob_path=f"blobs/sha256/{content_hash}.csv",
        content_noop=False,
    )


def test_canonical_json_and_hashes_have_precise_algorithms() -> None:
    payload = {"z": ["é", 2], "a": {"b": True}}

    serialized = canonical_json_bytes(payload)

    assert serialized == b'{"a":{"b":true},"z":["\xc3\xa9",2]}\n'
    assert canonical_json_sha256(payload) == hashlib.sha256(serialized[:-1]).hexdigest()

    columns = (
        ColumnSchema(name="YEAR", declared_type="NUMERIC"),
        ColumnSchema(name="BENE_GEO_LVL", declared_type="TEXT"),
    )
    expected_schema_payload = [
        {"name": "YEAR", "declared_type": "NUMERIC"},
        {"name": "BENE_GEO_LVL", "declared_type": "TEXT"},
    ]
    expected_header_payload = ["YEAR", "BENE_GEO_LVL"]
    assert (
        schema_sha256(columns)
        == hashlib.sha256(
            canonical_json_bytes(expected_schema_payload)[:-1]
        ).hexdigest()
    )
    assert (
        header_sha256(expected_header_payload)
        == hashlib.sha256(
            canonical_json_bytes(expected_header_payload)[:-1]
        ).hexdigest()
    )


def test_csv_validation_counts_logical_rows_and_reports_additions() -> None:
    evidence = validate_raw_csv(
        FIXTURE_PATH,
        fixture_schema(),
        expected_row_count=2,
    )

    assert evidence.header == fixture_header()
    assert evidence.row_count == 2
    assert evidence.header_sha256 == header_sha256(fixture_header())
    assert evidence.additive_columns == ("ADDITIVE_NOTE",)


def test_duplicate_csv_header_blocks_validation(tmp_path: Path) -> None:
    duplicate_path = tmp_path / "duplicate.csv"
    duplicate_path.write_text(
        "YEAR,YEAR\n2024,2024\n",
        encoding="utf-8",
        newline="",
    )
    columns = (
        ColumnSchema("YEAR", "NUMERIC"),
        ColumnSchema("YEAR", "NUMERIC"),
    )

    with pytest.raises(CsvValidationError, match=r"duplicate header.*YEAR"):
        validate_raw_csv(duplicate_path, columns)


def test_required_schema_failure_blocks_csv_validation() -> None:
    metadata = tuple(
        column for column in fixture_schema() if column.name != "BENES_OP_DLYS_PCT"
    )

    with pytest.raises(CsvValidationError, match="BENES_OP_DLYS_PCT"):
        validate_raw_csv(FIXTURE_PATH, metadata)


def test_incompatible_declared_type_blocks_csv_validation() -> None:
    metadata = tuple(
        replace(column, declared_type="TEXT")
        if column.name == "BENES_OP_DLYS_PCT"
        else column
        for column in fixture_schema()
    )

    with pytest.raises(CsvValidationError, match="incompatible declared type"):
        validate_raw_csv(FIXTURE_PATH, metadata)


def test_metadata_and_actual_header_must_reconcile() -> None:
    metadata = tuple(reversed(fixture_schema()))

    with pytest.raises(CsvValidationError, match="metadata header"):
        validate_raw_csv(FIXTURE_PATH, metadata)


def test_expected_row_count_must_reconcile() -> None:
    with pytest.raises(CsvValidationError, match=r"expected 3.*found 2"):
        validate_raw_csv(
            FIXTURE_PATH,
            fixture_schema(),
            expected_row_count=3,
        )


def test_malformed_grain_blocks_validation(tmp_path: Path) -> None:
    content = FIXTURE_PATH.read_text(encoding="utf-8").replace(
        "2024,County",
        "not-a-year,County",
        1,
    )
    malformed_path = tmp_path / "malformed.csv"
    malformed_path.write_text(content, encoding="utf-8", newline="")

    with pytest.raises(CsvValidationError, match=r"row 2.*YEAR"):
        validate_raw_csv(
            malformed_path,
            fixture_schema(),
            expected_row_count=2,
        )


def test_duplicate_source_grain_blocks_validation(tmp_path: Path) -> None:
    duplicate_path = tmp_path / "duplicate-grain.csv"
    with FIXTURE_PATH.open(encoding="utf-8", newline="") as fixture:
        rows = list(csv.reader(fixture))
    with duplicate_path.open("w", encoding="utf-8", newline="") as duplicate_file:
        writer = csv.writer(duplicate_file, lineterminator="\n")
        writer.writerows((rows[0], rows[1], rows[1]))

    with pytest.raises(
        CsvValidationError,
        match=rf"duplicate source grain.*{GRAIN_KEYS[0]}.*row 3.*row 2",
    ):
        validate_raw_csv(
            duplicate_path,
            fixture_schema(),
            expected_row_count=2,
        )


def test_valid_publication_is_content_addressed_and_reconciled(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    staged_path = output_root / ".tmp" / "fixture" / "download.partial"
    original = copy_fixture(staged_path)
    manifest = valid_manifest(staged_path)

    result = publish_snapshot(staged_path, output_root, manifest)

    assert result.blob_path.read_bytes() == original
    assert result.blob_path == output_root / manifest.blob_path
    assert result.manifest_path == (
        output_root / "manifests" / "cms_om_gv" / f"{manifest.pipeline_run_id}.json"
    )
    assert result.manifest_path.read_bytes().endswith(b"\n")
    assert json.loads(result.manifest_path.read_bytes()) == result.manifest.to_dict()
    assert not result.manifest.content_noop
    assert not result.manifest_noop
    assert not staged_path.exists()
    reconcile_manifest_file(result.manifest, result.blob_path)


def test_later_run_reuses_verified_blob_and_records_content_noop(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "raw"
    first_stage = output_root / ".tmp" / "first" / "download.partial"
    copy_fixture(first_stage)
    first = publish_snapshot(first_stage, output_root, valid_manifest(first_stage))

    second_stage = output_root / ".tmp" / "second" / "download.partial"
    copy_fixture(second_stage)
    second_manifest = valid_manifest(
        second_stage,
        run_id="cms-om-gv-fixture-002",
    )
    second = publish_snapshot(second_stage, output_root, second_manifest)

    assert second.blob_path == first.blob_path
    assert second.manifest.content_noop
    assert not second.manifest_noop
    assert len(list((output_root / "blobs" / "sha256").glob("*.csv"))) == 1
    assert len(list((output_root / "manifests" / "cms_om_gv").glob("*.json"))) == 2


def test_same_run_and_lineage_is_an_idempotent_manifest_noop(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    first_stage = output_root / ".tmp" / "same" / "download.partial"
    copy_fixture(first_stage)
    first_manifest = valid_manifest(first_stage)
    first = publish_snapshot(first_stage, output_root, first_manifest)

    rerun_stage = output_root / ".tmp" / "same-rerun" / "download.partial"
    copy_fixture(rerun_stage)
    rerun = publish_snapshot(rerun_stage, output_root, first_manifest)

    assert rerun.manifest == first.manifest
    assert rerun.manifest_noop
    assert not rerun_stage.exists()


def test_same_run_with_different_lineage_fails_without_overwrite(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "raw"
    first_stage = output_root / ".tmp" / "first" / "download.partial"
    copy_fixture(first_stage)
    first = publish_snapshot(first_stage, output_root, valid_manifest(first_stage))
    original_manifest_bytes = first.manifest_path.read_bytes()

    conflict_stage = output_root / ".tmp" / "conflict" / "download.partial"
    copy_fixture(conflict_stage)
    conflict = replace(
        valid_manifest(conflict_stage),
        retrieved_at_utc="2026-08-14T12:01:00Z",
    )

    with pytest.raises(ManifestConflictError):
        publish_snapshot(conflict_stage, output_root, conflict)

    assert first.manifest_path.read_bytes() == original_manifest_bytes


def test_corrupt_existing_blob_is_a_blocking_integrity_failure(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    first_stage = output_root / ".tmp" / "first" / "download.partial"
    copy_fixture(first_stage)
    first = publish_snapshot(first_stage, output_root, valid_manifest(first_stage))
    first.blob_path.write_bytes(b"corrupt")

    second_stage = output_root / ".tmp" / "second" / "download.partial"
    copy_fixture(second_stage)

    with pytest.raises(BlobIntegrityError):
        publish_snapshot(
            second_stage,
            output_root,
            valid_manifest(second_stage, run_id="cms-om-gv-fixture-002"),
        )


def test_failed_reconciliation_cannot_publish_final_artifacts(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    staged_path = output_root / ".tmp" / "bad" / "download.partial"
    copy_fixture(staged_path)
    bad_manifest = replace(valid_manifest(staged_path), byte_count=1)

    with pytest.raises(ManifestReconciliationError, match="byte count"):
        publish_snapshot(staged_path, output_root, bad_manifest)

    assert not (output_root / "blobs").exists()
    assert not (output_root / "manifests").exists()


@pytest.mark.parametrize(
    "run_id",
    ("", ".", "..", "../escape", "folder/name", "folder\\name", "has space"),
)
def test_invalid_run_ids_cannot_escape_manifest_directory(run_id: str) -> None:
    with pytest.raises(ValueError, match="run ID"):
        validate_run_id(run_id)
