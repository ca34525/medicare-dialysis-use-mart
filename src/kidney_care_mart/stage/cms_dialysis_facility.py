"""Verify one facility manifest and load its required raw strings into DuckDB."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import duckdb

from kidney_care_mart.contracts.cms_dialysis_facility import (
    CONTRACT_VERSION,
    REQUIRED_FIELDS,
    SOURCE_ID,
)
from kidney_care_mart.extract.cms_dialysis_facility import (
    FacilityManifestConflictError,
    FacilitySnapshotManifest,
    ReconciledFacilitySnapshot,
    load_and_reconcile_facility_snapshot,
)

RAW_SCHEMA: Final = "raw"
RAW_TABLE: Final = "cms_dialysis_facility"
AUDIT_TABLE: Final = "cms_dialysis_facility_load_audit"
LINEAGE_COLUMNS: Final = (
    "source_id",
    "source_manifest_run_id",
    "source_snapshot_sha256",
    "source_retrieved_at_utc",
    "source_release",
    "source_modified_at",
)


class FacilityStageLoadError(RuntimeError):
    """A verified facility snapshot cannot be loaded safely."""


class FacilityStageLoadConflictError(FacilityStageLoadError):
    """A final database already represents different facility lineage."""


@dataclass(frozen=True, slots=True)
class FacilityStageLoadResult:
    """Deterministic evidence returned by one facility raw load."""

    status: str
    database_path: Path
    manifest_path: Path
    blob_path: Path
    row_count: int
    distinct_ccn_count: int
    snapshot_sha256: str
    database_noop: bool


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _sql_string(value: str | None) -> str:
    if value is None:
        return "null::varchar"
    return "'" + value.replace("'", "''") + "'::varchar"


def _lineage(manifest: FacilitySnapshotManifest) -> tuple[str | None, ...]:
    return (
        SOURCE_ID,
        manifest.pipeline_run_id,
        manifest.content_sha256,
        manifest.retrieved_at_utc,
        manifest.source_release,
        manifest.source_modified_date,
    )


def _verify_existing_database(
    database_path: Path,
    snapshot: ReconciledFacilitySnapshot,
) -> int:
    manifest = snapshot.manifest
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            audit = connection.execute(
                f"""
                select source_id,
                       source_manifest_run_id,
                       source_snapshot_sha256,
                       source_retrieved_at_utc,
                       source_release,
                       source_modified_at,
                       contract_version,
                       row_count,
                       distinct_ccn_count,
                       page_count,
                       schema_sha256,
                       header_sha256
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
        raise FacilityStageLoadConflictError(
            "existing database is not a valid facility staging load"
        ) from error

    expected_lineage = _lineage(manifest)
    expected_audit = (
        *expected_lineage,
        CONTRACT_VERSION,
        manifest.csv_row_count,
        manifest.distinct_ccn_count,
        1,
        manifest.schema_sha256,
        manifest.header_sha256,
    )
    if audit != [expected_audit] or lineage != [expected_lineage]:
        raise FacilityStageLoadConflictError(
            "existing database represents a different facility manifest or lineage"
        )
    if row_count != manifest.csv_row_count:
        raise FacilityStageLoadConflictError(
            "existing database row count does not match its facility manifest"
        )
    return row_count


def _load_database(
    temporary_path: Path,
    snapshot: ReconciledFacilitySnapshot,
) -> None:
    manifest = snapshot.manifest
    required_headers = tuple(field.csv_header for field in REQUIRED_FIELDS)
    raw_columns_sql = ",\n".join(
        f"{_quoted(name)} varchar not null" for name in required_headers
    )
    lineage_columns_sql = ",\n".join(
        f"{_quoted(name)} varchar" for name in LINEAGE_COLUMNS
    )
    insert_columns = (*required_headers, *LINEAGE_COLUMNS)
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
                source_snapshot_sha256 varchar not null,
                source_retrieved_at_utc varchar not null,
                source_release varchar,
                source_modified_at varchar,
                contract_version varchar not null,
                row_count bigint not null,
                distinct_ccn_count bigint not null,
                page_count bigint not null,
                schema_sha256 varchar not null,
                header_sha256 varchar not null
            )
            """
        )
        lineage = _lineage(manifest)
        selected_columns = ", ".join(_quoted(name) for name in required_headers)
        lineage_literals = ", ".join(_sql_string(value) for value in lineage)
        csv_path = _sql_string(str(snapshot.blob_path))
        connection.execute(
            f"""
            insert into {RAW_SCHEMA}.{RAW_TABLE}
                ({", ".join(_quoted(name) for name in insert_columns)})
            select {selected_columns}, {lineage_literals}
            from read_csv(
                {csv_path},
                header = true,
                all_varchar = true,
                nullstr = '__KIDNEY_CARE_MART_NULL_SENTINEL__',
                strict_mode = true,
                parallel = true
            )
            """
        )
        loaded_rows = connection.execute(
            f"select count(*) from {RAW_SCHEMA}.{RAW_TABLE}"
        ).fetchone()[0]
        if loaded_rows != manifest.csv_row_count:
            raise FacilityStageLoadError(
                "loaded facility row count does not match the verified manifest: "
                f"{loaded_rows} != {manifest.csv_row_count}"
            )
        connection.execute(
            f"insert into {RAW_SCHEMA}.{AUDIT_TABLE} "
            "values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                *lineage,
                CONTRACT_VERSION,
                loaded_rows,
                manifest.distinct_ccn_count,
                1,
                manifest.schema_sha256,
                manifest.header_sha256,
            ],
        )
        connection.execute("checkpoint")
    finally:
        connection.close()


def load_cms_dialysis_facility_snapshot(
    manifest_path: Path,
    raw_root: Path,
    database_path: Path,
) -> FacilityStageLoadResult:
    """Verify and atomically load one immutable facility snapshot."""
    try:
        snapshot = load_and_reconcile_facility_snapshot(manifest_path, raw_root)
    except (FacilityManifestConflictError, OSError, ValueError) as error:
        raise FacilityStageLoadError(
            f"facility snapshot integrity validation failed: {error}"
        ) from error

    final_database = database_path.resolve()
    if final_database.exists():
        row_count = _verify_existing_database(final_database, snapshot)
        return FacilityStageLoadResult(
            status="database_noop",
            database_path=final_database,
            manifest_path=snapshot.manifest_path,
            blob_path=snapshot.blob_path,
            row_count=row_count,
            distinct_ccn_count=snapshot.manifest.distinct_ccn_count,
            snapshot_sha256=snapshot.manifest.content_sha256,
            database_noop=True,
        )

    final_database.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = final_database.with_name(
        f".{final_database.name}.{snapshot.manifest.pipeline_run_id}.partial"
    )
    if temporary_path.exists():
        raise FacilityStageLoadConflictError(
            f"database staging path already exists: {temporary_path}"
        )
    try:
        _load_database(temporary_path, snapshot)
        try:
            os.link(temporary_path, final_database)
        except FileExistsError as error:
            raise FacilityStageLoadConflictError(
                f"database path appeared concurrently: {final_database}"
            ) from error
    except FacilityStageLoadError:
        raise
    except (duckdb.Error, OSError) as error:
        raise FacilityStageLoadError(f"facility raw load failed: {error}") from error
    finally:
        temporary_path.unlink(missing_ok=True)
        Path(f"{temporary_path}.wal").unlink(missing_ok=True)

    return FacilityStageLoadResult(
        status="loaded",
        database_path=final_database,
        manifest_path=snapshot.manifest_path,
        blob_path=snapshot.blob_path,
        row_count=snapshot.manifest.csv_row_count,
        distinct_ccn_count=snapshot.manifest.distinct_ccn_count,
        snapshot_sha256=snapshot.manifest.content_sha256,
        database_noop=False,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and load one local CMS facility snapshot into DuckDB."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the network-free facility snapshot loader command."""
    arguments = _parser().parse_args(argv)
    result = load_cms_dialysis_facility_snapshot(
        manifest_path=arguments.manifest,
        raw_root=arguments.raw_root,
        database_path=arguments.database,
    )
    print(
        json.dumps(
            {
                "blob_path": str(result.blob_path),
                "database_noop": result.database_noop,
                "database_path": str(result.database_path),
                "distinct_ccn_count": result.distinct_ccn_count,
                "manifest_path": str(result.manifest_path),
                "row_count": result.row_count,
                "snapshot_sha256": result.snapshot_sha256,
                "status": result.status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
