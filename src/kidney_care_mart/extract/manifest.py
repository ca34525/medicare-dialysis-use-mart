"""Raw CSV validation and immutable content-addressed publication."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Final

from kidney_care_mart.contracts.cms_om_gv import (
    GRAIN_KEYS,
    ColumnSchema,
    validate_grain_keys,
    validate_schema,
)

_RUN_ID_PATTERN: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SOURCE_ID_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class CsvValidationError(RuntimeError):
    """Raw CSV evidence does not satisfy metadata or the source contract."""


class ManifestPublicationError(RuntimeError):
    """Base class for immutable publication failures."""


class ManifestReconciliationError(ManifestPublicationError):
    """A manifest field does not reconcile to its referenced bytes."""


class ManifestConflictError(ManifestPublicationError):
    """A run-scoped manifest already exists with different lineage."""


class BlobIntegrityError(ManifestPublicationError):
    """An existing content-addressed blob does not match its identity."""


@dataclass(frozen=True, slots=True)
class CsvEvidence:
    """Deterministic evidence calculated from a raw CSV file."""

    header: tuple[str, ...]
    row_count: int
    header_sha256: str
    additive_columns: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    """Complete lineage for one immutable source snapshot reference."""

    manifest_format_version: int
    logical_source_id: str
    pipeline_run_id: str
    extractor_version: str
    contract_version: str
    official_catalog_url: str
    official_landing_url: str
    stable_dataset_id: str
    resolved_csv_url: str
    retrieved_at_utc: str
    source_release: str | None
    source_modified_date: str | None
    http_etag: str | None
    http_last_modified: str | None
    content_sha256: str
    byte_count: int
    csv_row_count: int
    transport_mode: str
    page_count: int
    record_count: int
    columns: tuple[ColumnSchema, ...]
    schema_sha256: str
    header_sha256: str
    additive_columns: tuple[str, ...]
    blob_path: str
    content_noop: bool

    def to_dict(self) -> dict[str, Any]:
        """Return the stable public JSON representation."""
        return {
            "manifest_format_version": self.manifest_format_version,
            "pipeline": {
                "extractor_version": self.extractor_version,
                "run_id": self.pipeline_run_id,
            },
            "source": {
                "catalog_url": self.official_catalog_url,
                "landing_url": self.official_landing_url,
                "logical_source_id": self.logical_source_id,
                "resolved_csv_url": self.resolved_csv_url,
                "stable_dataset_id": self.stable_dataset_id,
            },
            "retrieval": {
                "http_etag": self.http_etag,
                "http_last_modified": self.http_last_modified,
                "retrieved_at_utc": self.retrieved_at_utc,
                "source_modified_date": self.source_modified_date,
                "source_release": self.source_release,
            },
            "content": {
                "byte_count": self.byte_count,
                "csv_row_count": self.csv_row_count,
                "sha256": self.content_sha256,
            },
            "transport": {
                "mode": self.transport_mode,
                "page_count": self.page_count,
                "record_count": self.record_count,
            },
            "schema": {
                "additive_columns": list(self.additive_columns),
                "columns": [
                    {
                        "name": column.name,
                        "declared_type": column.declared_type,
                    }
                    for column in self.columns
                ],
                "contract_version": self.contract_version,
                "header_sha256": self.header_sha256,
                "schema_sha256": self.schema_sha256,
            },
            "storage": {
                "blob_path": self.blob_path,
                "content_noop": self.content_noop,
            },
        }


@dataclass(frozen=True, slots=True)
class SnapshotPublication:
    """Paths and final manifest state returned by atomic publication."""

    manifest: SnapshotManifest
    blob_path: Path
    manifest_path: Path
    manifest_noop: bool


def _canonical_json_payload(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize canonical UTF-8 JSON with one final newline."""
    return _canonical_json_payload(value) + b"\n"


def canonical_json_sha256(value: object) -> str:
    """Hash canonical JSON payload bytes, excluding presentation newline."""
    return hashlib.sha256(_canonical_json_payload(value)).hexdigest()


def schema_sha256(columns: Sequence[ColumnSchema]) -> str:
    """Hash ordered name/type metadata pairs using canonical JSON."""
    payload = [
        {"name": column.name, "declared_type": column.declared_type}
        for column in columns
    ]
    return canonical_json_sha256(payload)


def header_sha256(header: Sequence[str]) -> str:
    """Hash ordered raw CSV labels using canonical JSON."""
    return canonical_json_sha256(list(header))


def _describe_contract_issues(columns: Sequence[ColumnSchema]) -> tuple[str, ...]:
    result = validate_schema(columns)
    return tuple(issue.message for issue in result.issues)


def validate_raw_csv(
    path: Path,
    metadata_columns: Sequence[ColumnSchema],
    *,
    expected_row_count: int | None = None,
) -> CsvEvidence:
    """Stream-validate raw rows against ordered CMS metadata and grain rules."""
    columns = tuple(metadata_columns)
    if expected_row_count is not None and expected_row_count < 0:
        raise ValueError("expected_row_count cannot be negative")

    metadata_names = tuple(column.name for column in columns)
    duplicate_metadata = sorted(
        name for name, count in Counter(metadata_names).items() if count > 1
    )
    if duplicate_metadata:
        raise CsvValidationError(
            "CMS metadata contains duplicate header labels: "
            + ", ".join(duplicate_metadata)
        )

    try:
        with path.open(encoding="utf-8", newline="") as source_file:
            reader = csv.reader(source_file, strict=True)
            try:
                raw_header = next(reader)
            except StopIteration as error:
                raise CsvValidationError("raw CSV is empty") from error

            duplicate_header = sorted(
                name for name, count in Counter(raw_header).items() if count > 1
            )
            if duplicate_header:
                raise CsvValidationError(
                    "raw CSV contains duplicate header labels: "
                    + ", ".join(duplicate_header)
                )

            contract_issues = _describe_contract_issues(columns)
            if contract_issues:
                raise CsvValidationError(
                    "CMS metadata violates the required contract: "
                    + "; ".join(contract_issues)
                )

            header = tuple(raw_header)
            if header != metadata_names:
                raise CsvValidationError(
                    "raw CSV header does not match the ordered CMS metadata header"
                )

            row_count = 0
            first_row_by_grain: dict[tuple[str, ...], int] = {}
            for row in reader:
                row_count += 1
                if len(row) != len(header):
                    raise CsvValidationError(
                        f"CSV row {reader.line_num} has {len(row)} values; "
                        f"expected {len(header)}"
                    )
                raw_row = dict(zip(header, row, strict=True))
                grain_result = validate_grain_keys(raw_row)
                if not grain_result.is_valid:
                    messages = "; ".join(
                        f"{issue.field}: {issue.message}"
                        for issue in grain_result.issues
                    )
                    raise CsvValidationError(
                        f"CSV row {reader.line_num} has invalid grain keys: {messages}"
                    )
                grain = tuple(raw_row[key] for key in GRAIN_KEYS)
                first_row_number = first_row_by_grain.setdefault(grain, reader.line_num)
                if first_row_number != reader.line_num:
                    grain_labels = ", ".join(GRAIN_KEYS)
                    raise CsvValidationError(
                        f"duplicate source grain ({grain_labels}) at row "
                        f"{reader.line_num}; first seen at row {first_row_number}"
                    )
    except UnicodeDecodeError as error:
        raise CsvValidationError("raw CSV is not valid UTF-8") from error
    except csv.Error as error:
        raise CsvValidationError(f"raw CSV parsing failed: {error}") from error

    if expected_row_count is not None and row_count != expected_row_count:
        raise CsvValidationError(
            f"CSV row count mismatch: expected {expected_row_count}, found {row_count}"
        )

    contract_result = validate_schema(columns)
    return CsvEvidence(
        header=header,
        row_count=row_count,
        header_sha256=header_sha256(header),
        additive_columns=contract_result.additive_columns,
    )


def validate_run_id(run_id: str) -> None:
    """Reject path syntax and unstable identifiers before creating paths."""
    if run_id in {".", ".."} or _RUN_ID_PATTERN.fullmatch(run_id) is None:
        raise ValueError(
            "invalid pipeline run ID; use 1-128 ASCII letters, digits, '.', '_', "
            "or '-', beginning with a letter or digit"
        )


def _validate_manifest_shape(manifest: SnapshotManifest) -> None:
    validate_run_id(manifest.pipeline_run_id)
    if _SOURCE_ID_PATTERN.fullmatch(manifest.logical_source_id) is None:
        raise ValueError("invalid logical source ID")
    if _SHA256_PATTERN.fullmatch(manifest.content_sha256) is None:
        raise ValueError("invalid content SHA-256")
    expected_blob_path = (
        PurePosixPath("blobs") / "sha256" / f"{manifest.content_sha256}.csv"
    ).as_posix()
    if manifest.blob_path != expected_blob_path:
        raise ManifestReconciliationError(
            "manifest blob path does not match its content SHA-256"
        )
    if manifest.transport_mode != "full_csv":
        raise ManifestReconciliationError("CMS transport mode must be full_csv")
    if manifest.page_count != 1:
        raise ManifestReconciliationError("CMS full CSV page_count must be 1")
    if manifest.record_count != manifest.csv_row_count:
        raise ManifestReconciliationError(
            "manifest record count does not match CSV row count"
        )
    if tuple(sorted(manifest.additive_columns)) != manifest.additive_columns:
        raise ManifestReconciliationError("additive columns must be sorted")


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def reconcile_manifest_file(manifest: SnapshotManifest, path: Path) -> None:
    """Independently reconcile all manifest evidence to one local CSV."""
    _validate_manifest_shape(manifest)
    actual_hash, actual_bytes = _hash_file(path)
    if actual_bytes != manifest.byte_count:
        raise ManifestReconciliationError(
            "manifest byte count does not match the referenced CSV"
        )
    if actual_hash != manifest.content_sha256:
        raise ManifestReconciliationError(
            "manifest content SHA-256 does not match the referenced CSV"
        )
    expected_schema_hash = schema_sha256(manifest.columns)
    if expected_schema_hash != manifest.schema_sha256:
        raise ManifestReconciliationError(
            "manifest schema hash does not match its ordered columns"
        )
    evidence = validate_raw_csv(
        path,
        manifest.columns,
        expected_row_count=manifest.csv_row_count,
    )
    if evidence.header_sha256 != manifest.header_sha256:
        raise ManifestReconciliationError(
            "manifest header hash does not match the referenced CSV"
        )
    if evidence.additive_columns != manifest.additive_columns:
        raise ManifestReconciliationError(
            "manifest additive columns do not match contract validation"
        )


def _safe_relative_target(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ManifestPublicationError("generated path escapes the output root")
    target = root.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise ManifestPublicationError("generated path escapes the output root")
    return target


def _verify_existing_blob(manifest: SnapshotManifest, blob_path: Path) -> None:
    try:
        reconcile_manifest_file(manifest, blob_path)
    except (CsvValidationError, ManifestReconciliationError) as error:
        raise BlobIntegrityError(
            f"existing content-addressed blob failed integrity checks: {blob_path}"
        ) from error


def _write_atomic_new_file(path: Path, content: bytes) -> None:
    """Publish bytes atomically without ever overwriting an existing file."""
    temporary_path = path.with_name(f".{path.name}.partial")
    if temporary_path.exists():
        raise ManifestPublicationError(
            f"manifest staging path already exists: {temporary_path}"
        )
    try:
        with temporary_path.open("xb") as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        try:
            os.link(temporary_path, path)
        except FileExistsError:
            raise
    finally:
        temporary_path.unlink(missing_ok=True)


def publish_snapshot(
    staged_path: Path,
    output_root: Path,
    manifest: SnapshotManifest,
) -> SnapshotPublication:
    """Validate and atomically publish one immutable blob and run manifest."""
    root = output_root.resolve()
    staged = staged_path.resolve()
    if not staged.is_relative_to(root):
        raise ManifestPublicationError(
            "staged snapshot must be on the configured output volume"
        )

    _validate_manifest_shape(manifest)
    reconcile_manifest_file(manifest, staged)

    blob_path = _safe_relative_target(root, manifest.blob_path)
    manifest_path = (
        root
        / "manifests"
        / manifest.logical_source_id
        / f"{manifest.pipeline_run_id}.json"
    )

    if manifest_path.exists():
        try:
            existing_dict = json.loads(manifest_path.read_bytes())
            existing_noop = existing_dict["storage"]["content_noop"]
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ManifestConflictError(
                f"existing manifest is invalid: {manifest_path}"
            ) from error
        if not isinstance(existing_noop, bool):
            raise ManifestConflictError(
                f"existing manifest has invalid no-op state: {manifest_path}"
            )
        candidate = replace(manifest, content_noop=existing_noop)
        if canonical_json_bytes(existing_dict) != manifest_path.read_bytes():
            raise ManifestConflictError(
                f"existing manifest is not canonical: {manifest_path}"
            )
        if existing_dict != candidate.to_dict():
            raise ManifestConflictError(
                "pipeline run ID already exists with different content or lineage: "
                f"{manifest.pipeline_run_id}"
            )
        if not blob_path.exists():
            raise BlobIntegrityError(
                f"existing manifest references a missing blob: {blob_path}"
            )
        _verify_existing_blob(candidate, blob_path)
        staged.unlink(missing_ok=True)
        return SnapshotPublication(
            manifest=candidate,
            blob_path=blob_path,
            manifest_path=manifest_path,
            manifest_noop=True,
        )

    content_noop = blob_path.exists()
    final_manifest = replace(manifest, content_noop=content_noop)
    if content_noop:
        _verify_existing_blob(final_manifest, blob_path)
        staged.unlink()
    else:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(staged, blob_path)
        except FileExistsError:
            content_noop = True
            final_manifest = replace(manifest, content_noop=True)
            _verify_existing_blob(final_manifest, blob_path)
        else:
            _verify_existing_blob(final_manifest, blob_path)
        staged.unlink(missing_ok=True)

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = canonical_json_bytes(final_manifest.to_dict())
    try:
        _write_atomic_new_file(manifest_path, manifest_bytes)
    except FileExistsError as error:
        raise ManifestConflictError(
            f"pipeline run manifest appeared concurrently: {manifest_path}"
        ) from error

    return SnapshotPublication(
        manifest=final_manifest,
        blob_path=blob_path,
        manifest_path=manifest_path,
        manifest_noop=False,
    )
