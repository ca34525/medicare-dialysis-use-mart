"""Verify one CMS snapshot manifest and load its raw strings into DuckDB."""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final

import duckdb

from kidney_care_mart.contracts.cms_om_gv import (
    CONTRACT_VERSION,
    REQUIRED_COLUMNS,
    SOURCE_ID,
    ColumnSchema,
)
from kidney_care_mart.extract.manifest import (
    CsvValidationError,
    ManifestReconciliationError,
    SnapshotManifest,
    canonical_json_bytes,
    reconcile_manifest_file,
)

SUPPORTED_MANIFEST_FORMAT_VERSION: Final = 1
RAW_SCHEMA: Final = "raw"
RAW_TABLE: Final = "cms_om_gv"
AUDIT_TABLE: Final = "cms_om_gv_load_audit"
LINEAGE_COLUMNS: Final = (
    "source_id",
    "source_manifest_run_id",
    "source_content_sha256",
    "source_retrieved_at_utc",
    "source_modified_at",
)


class StageLoadError(RuntimeError):
    """A local source snapshot cannot be verified or loaded safely."""


class StageLoadConflictError(StageLoadError):
    """A final DuckDB path already represents different source lineage."""


@dataclass(frozen=True, slots=True)
class StageLoadResult:
    """Deterministic evidence returned by one raw snapshot load."""

    status: str
    database_path: Path
    manifest_path: Path
    blob_path: Path
    row_count: int
    content_sha256: str
    database_noop: bool


def _mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise StageLoadError(f"manifest field {field} must be an object")
    return value


def _sequence(value: object, *, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise StageLoadError(f"manifest field {field} must be an array")
    return value


def _string(
    value: object,
    *,
    field: str,
    nullable: bool = False,
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise StageLoadError(f"manifest field {field} must be text")
    return value


def _integer(value: object, *, field: str) -> int:
    if type(value) is not int:
        raise StageLoadError(f"manifest field {field} must be an integer")
    return value


def _boolean(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise StageLoadError(f"manifest field {field} must be boolean")
    return value


def _manifest_from_payload(payload: Mapping[str, Any]) -> SnapshotManifest:
    """Parse the public Plan 002 JSON shape without trusting its values."""
    try:
        pipeline = _mapping(payload["pipeline"], field="pipeline")
        source = _mapping(payload["source"], field="source")
        retrieval = _mapping(payload["retrieval"], field="retrieval")
        content = _mapping(payload["content"], field="content")
        transport = _mapping(payload["transport"], field="transport")
        schema = _mapping(payload["schema"], field="schema")
        storage = _mapping(payload["storage"], field="storage")
        raw_columns = _sequence(schema["columns"], field="schema.columns")
        columns = tuple(
            ColumnSchema(
                name=_string(
                    _mapping(column, field=f"schema.columns[{index}]")["name"],
                    field=f"schema.columns[{index}].name",
                ),
                declared_type=_string(
                    _mapping(column, field=f"schema.columns[{index}]")["declared_type"],
                    field=f"schema.columns[{index}].declared_type",
                ),
            )
            for index, column in enumerate(raw_columns)
        )
        raw_additives = _sequence(
            schema["additive_columns"],
            field="schema.additive_columns",
        )
        additive_columns = tuple(
            _string(value, field=f"schema.additive_columns[{index}]")
            for index, value in enumerate(raw_additives)
        )
        return SnapshotManifest(
            manifest_format_version=_integer(
                payload["manifest_format_version"],
                field="manifest_format_version",
            ),
            logical_source_id=_string(
                source["logical_source_id"], field="source.logical_source_id"
            ),
            pipeline_run_id=_string(pipeline["run_id"], field="pipeline.run_id"),
            extractor_version=_string(
                pipeline["extractor_version"], field="pipeline.extractor_version"
            ),
            contract_version=_string(
                schema["contract_version"], field="schema.contract_version"
            ),
            official_catalog_url=_string(
                source["catalog_url"], field="source.catalog_url"
            ),
            official_landing_url=_string(
                source["landing_url"], field="source.landing_url"
            ),
            stable_dataset_id=_string(
                source["stable_dataset_id"], field="source.stable_dataset_id"
            ),
            resolved_csv_url=_string(
                source["resolved_csv_url"], field="source.resolved_csv_url"
            ),
            retrieved_at_utc=_string(
                retrieval["retrieved_at_utc"], field="retrieval.retrieved_at_utc"
            ),
            source_release=_string(
                retrieval["source_release"],
                field="retrieval.source_release",
                nullable=True,
            ),
            source_modified_date=_string(
                retrieval["source_modified_date"],
                field="retrieval.source_modified_date",
                nullable=True,
            ),
            http_etag=_string(
                retrieval["http_etag"],
                field="retrieval.http_etag",
                nullable=True,
            ),
            http_last_modified=_string(
                retrieval["http_last_modified"],
                field="retrieval.http_last_modified",
                nullable=True,
            ),
            content_sha256=_string(content["sha256"], field="content.sha256"),
            byte_count=_integer(content["byte_count"], field="content.byte_count"),
            csv_row_count=_integer(
                content["csv_row_count"], field="content.csv_row_count"
            ),
            transport_mode=_string(transport["mode"], field="transport.mode"),
            page_count=_integer(transport["page_count"], field="transport.page_count"),
            record_count=_integer(
                transport["record_count"], field="transport.record_count"
            ),
            columns=columns,
            schema_sha256=_string(
                schema["schema_sha256"], field="schema.schema_sha256"
            ),
            header_sha256=_string(
                schema["header_sha256"], field="schema.header_sha256"
            ),
            additive_columns=additive_columns,
            blob_path=_string(storage["blob_path"], field="storage.blob_path"),
            content_noop=_boolean(
                storage["content_noop"], field="storage.content_noop"
            ),
        )
    except KeyError as error:
        raise StageLoadError(
            f"manifest is missing required field: {error.args[0]}"
        ) from error


def _load_manifest(path: Path) -> SnapshotManifest:
    try:
        manifest_bytes = path.read_bytes()
    except OSError as error:
        raise StageLoadError(f"cannot read manifest: {path}") from error
    try:
        payload = json.loads(manifest_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StageLoadError("manifest is not valid UTF-8 JSON") from error
    if not isinstance(payload, dict):
        raise StageLoadError("manifest root must be an object")
    if canonical_json_bytes(payload) != manifest_bytes:
        raise StageLoadError("manifest must use canonical Plan 002 JSON encoding")
    manifest = _manifest_from_payload(payload)
    if manifest.manifest_format_version != SUPPORTED_MANIFEST_FORMAT_VERSION:
        raise StageLoadError(
            f"unsupported manifest format version: {manifest.manifest_format_version}"
        )
    if manifest.logical_source_id != SOURCE_ID:
        raise StageLoadError(
            f"manifest source must be {SOURCE_ID}; found {manifest.logical_source_id}"
        )
    if manifest.contract_version != CONTRACT_VERSION:
        raise StageLoadError(
            f"unsupported CMS contract version: {manifest.contract_version}"
        )
    return manifest


def _resolve_blob(raw_root: Path, manifest: SnapshotManifest) -> Path:
    relative = PurePosixPath(manifest.blob_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise StageLoadError("manifest blob path escapes the configured raw root")
    root = raw_root.resolve()
    blob = root.joinpath(*relative.parts).resolve()
    if not blob.is_relative_to(root):
        raise StageLoadError("manifest blob path escapes the configured raw root")
    return blob


def _verify_local_snapshot(
    manifest_path: Path,
    raw_root: Path,
) -> tuple[SnapshotManifest, Path]:
    root = raw_root.resolve()
    resolved_manifest = manifest_path.resolve()
    manifests_root = (root / "manifests").resolve()
    if not resolved_manifest.is_relative_to(manifests_root):
        raise StageLoadError("manifest path must be beneath the configured raw root")
    manifest = _load_manifest(resolved_manifest)
    blob_path = _resolve_blob(root, manifest)
    try:
        reconcile_manifest_file(manifest, blob_path)
    except (OSError, CsvValidationError, ManifestReconciliationError) as error:
        raise StageLoadError(
            f"snapshot integrity validation failed: {error}"
        ) from error
    return manifest, blob_path


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _expected_lineage(manifest: SnapshotManifest) -> tuple[str | None, ...]:
    return (
        manifest.logical_source_id,
        manifest.pipeline_run_id,
        manifest.content_sha256,
        manifest.retrieved_at_utc,
        manifest.source_modified_date,
    )


def _verify_existing_database(
    database_path: Path,
    manifest: SnapshotManifest,
) -> int:
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            audit = connection.execute(
                f"""
                select
                    source_id,
                    source_manifest_run_id,
                    content_sha256,
                    source_retrieved_at_utc,
                    source_modified_at,
                    row_count
                from {RAW_SCHEMA}.{AUDIT_TABLE}
                """
            ).fetchall()
            row_count = connection.execute(
                f"select count(*) from {RAW_SCHEMA}.{RAW_TABLE}"
            ).fetchone()[0]
            lineage = connection.execute(
                f"""
                select distinct {", ".join(LINEAGE_COLUMNS)}
                from {RAW_SCHEMA}.{RAW_TABLE}
                """
            ).fetchall()
    except (duckdb.Error, OSError) as error:
        raise StageLoadConflictError(
            "existing database is not a valid CMS staging load"
        ) from error
    expected = _expected_lineage(manifest)
    expected_audit = (*expected, manifest.csv_row_count)
    if audit != [expected_audit] or lineage != [expected]:
        raise StageLoadConflictError(
            "existing database represents a different manifest or lineage"
        )
    if row_count != manifest.csv_row_count:
        raise StageLoadConflictError(
            "existing database row count does not match its manifest"
        )
    return row_count


def _load_database(
    temporary_path: Path,
    blob_path: Path,
    manifest: SnapshotManifest,
) -> None:
    required_names = tuple(REQUIRED_COLUMNS)
    raw_columns_sql = ",\n".join(
        f"{_quoted(name)} varchar not null" for name in required_names
    )
    lineage_columns_sql = ",\n".join(
        f"{_quoted(name)} varchar" for name in LINEAGE_COLUMNS
    )
    insert_columns = (*required_names, *LINEAGE_COLUMNS)
    insert_sql = (
        f"insert into {RAW_SCHEMA}.{RAW_TABLE} "
        f"({', '.join(_quoted(name) for name in insert_columns)}) "
        f"values ({', '.join('?' for _ in insert_columns)})"
    )
    connection = duckdb.connect(str(temporary_path))
    try:
        connection.execute(f"create schema {RAW_SCHEMA}")
        connection.execute(
            f"""
            create table {RAW_SCHEMA}.{RAW_TABLE} (
                {raw_columns_sql},
                {lineage_columns_sql}
            )
            """
        )
        connection.execute(
            f"""
            create table {RAW_SCHEMA}.{AUDIT_TABLE} (
                source_id varchar not null,
                source_manifest_run_id varchar not null,
                content_sha256 varchar not null,
                source_retrieved_at_utc varchar not null,
                source_modified_at varchar,
                row_count bigint not null,
                schema_sha256 varchar not null,
                header_sha256 varchar not null
            )
            """
        )
        lineage = _expected_lineage(manifest)
        batch: list[tuple[str | None, ...]] = []
        loaded_rows = 0
        with blob_path.open(encoding="utf-8", newline="") as source_file:
            reader = csv.DictReader(source_file, strict=True)
            for row in reader:
                batch.append(tuple(row[name] for name in required_names) + lineage)
                if len(batch) == 1000:
                    connection.executemany(insert_sql, batch)
                    loaded_rows += len(batch)
                    batch.clear()
            if batch:
                connection.executemany(insert_sql, batch)
                loaded_rows += len(batch)
        if loaded_rows != manifest.csv_row_count:
            raise StageLoadError(
                "loaded row count does not match the verified manifest: "
                f"{loaded_rows} != {manifest.csv_row_count}"
            )
        connection.execute(
            f"""
            insert into {RAW_SCHEMA}.{AUDIT_TABLE} values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                *lineage,
                loaded_rows,
                manifest.schema_sha256,
                manifest.header_sha256,
            ],
        )
        connection.execute("checkpoint")
    finally:
        connection.close()


def load_cms_om_gv_snapshot(
    manifest_path: Path,
    raw_root: Path,
    database_path: Path,
) -> StageLoadResult:
    """Verify and atomically load one immutable CMS snapshot into DuckDB."""
    resolved_manifest = manifest_path.resolve()
    manifest, blob_path = _verify_local_snapshot(resolved_manifest, raw_root)
    final_database = database_path.resolve()
    if final_database.exists():
        row_count = _verify_existing_database(final_database, manifest)
        return StageLoadResult(
            status="database_noop",
            database_path=final_database,
            manifest_path=resolved_manifest,
            blob_path=blob_path,
            row_count=row_count,
            content_sha256=manifest.content_sha256,
            database_noop=True,
        )

    final_database.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = final_database.with_name(
        f".{final_database.name}.{manifest.pipeline_run_id}.partial"
    )
    if temporary_path.exists():
        raise StageLoadConflictError(
            f"database staging path already exists: {temporary_path}"
        )
    try:
        _load_database(temporary_path, blob_path, manifest)
        try:
            os.link(temporary_path, final_database)
        except FileExistsError as error:
            raise StageLoadConflictError(
                f"database path appeared concurrently: {final_database}"
            ) from error
    except StageLoadError:
        raise
    except (csv.Error, duckdb.Error, OSError) as error:
        raise StageLoadError(f"CMS raw load failed: {error}") from error
    finally:
        temporary_path.unlink(missing_ok=True)
        Path(f"{temporary_path}.wal").unlink(missing_ok=True)

    return StageLoadResult(
        status="loaded",
        database_path=final_database,
        manifest_path=resolved_manifest,
        blob_path=blob_path,
        row_count=manifest.csv_row_count,
        content_sha256=manifest.content_sha256,
        database_noop=False,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and load one local CMS raw snapshot into DuckDB."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the network-free CMS snapshot loader command."""
    arguments = _build_parser().parse_args(argv)
    result = load_cms_om_gv_snapshot(
        manifest_path=arguments.manifest,
        raw_root=arguments.raw_root,
        database_path=arguments.database,
    )
    print(
        json.dumps(
            {
                "blob_path": str(result.blob_path),
                "content_sha256": result.content_sha256,
                "database_noop": result.database_noop,
                "database_path": str(result.database_path),
                "manifest_path": str(result.manifest_path),
                "row_count": result.row_count,
                "status": result.status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
