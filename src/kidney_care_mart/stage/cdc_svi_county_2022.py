"""Verify one paginated SVI manifest and load raw attribute tokens to DuckDB."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import duckdb

from kidney_care_mart.contracts.cdc_svi_county_2022 import (
    REQUIRED_FIELDS,
    SOURCE_ID,
)
from kidney_care_mart.extract.cdc_svi_county_2022 import (
    ReconciledSviSnapshot,
    SviExtractionError,
    load_and_reconcile_svi_snapshot,
)

RAW_SCHEMA: Final = "raw"
RAW_TABLE: Final = "cdc_svi_county_2022"
AUDIT_TABLE: Final = "cdc_svi_county_2022_load_audit"
LINEAGE_COLUMNS: Final = (
    "source_id",
    "source_manifest_run_id",
    "source_snapshot_sha256",
    "source_retrieved_at_utc",
    "source_modified_at",
    "source_page_index",
    "source_page_offset",
    "source_page_sha256",
)


class SviStageLoadError(RuntimeError):
    """A local SVI snapshot cannot be verified or loaded safely."""


class SviStageLoadConflictError(SviStageLoadError):
    """A final DuckDB path already represents different SVI lineage."""


@dataclass(frozen=True, slots=True)
class SviStageLoadResult:
    """Deterministic evidence returned by one SVI raw snapshot load."""

    status: str
    database_path: Path
    manifest_path: Path
    page_paths: tuple[Path, ...]
    page_count: int
    row_count: int
    snapshot_sha256: str
    database_noop: bool


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _base_lineage(snapshot: ReconciledSviSnapshot) -> tuple[str | None, ...]:
    manifest = snapshot.manifest
    return (
        SOURCE_ID,
        manifest.pipeline_run_id,
        manifest.snapshot_sha256,
        manifest.retrieved_at_utc,
        manifest.source_edit_at_utc,
    )


def _raw_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SviStageLoadError(
            f"raw attribute {field} was not preserved as text or null"
        )
    return value


def _verify_existing_database(
    database_path: Path,
    snapshot: ReconciledSviSnapshot,
) -> int:
    manifest = snapshot.manifest
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            audit = connection.execute(
                f"""
                select
                    source_id,
                    source_manifest_run_id,
                    snapshot_sha256,
                    source_retrieved_at_utc,
                    source_modified_at,
                    page_count,
                    row_count,
                    schema_sha256
                from {RAW_SCHEMA}.{AUDIT_TABLE}
                """
            ).fetchall()
            row_count = connection.execute(
                f"select count(*) from {RAW_SCHEMA}.{RAW_TABLE}"
            ).fetchone()[0]
            base_lineage = connection.execute(
                f"""
                select distinct
                    source_id,
                    source_manifest_run_id,
                    source_snapshot_sha256,
                    source_retrieved_at_utc,
                    source_modified_at
                from {RAW_SCHEMA}.{RAW_TABLE}
                """
            ).fetchall()
            page_lineage = connection.execute(
                f"""
                select
                    source_page_index,
                    source_page_offset,
                    source_page_sha256,
                    count(*)
                from {RAW_SCHEMA}.{RAW_TABLE}
                group by all
                order by source_page_index
                """
            ).fetchall()
    except (duckdb.Error, OSError) as error:
        raise SviStageLoadConflictError(
            "existing database is not a valid SVI staging load"
        ) from error

    expected_base = _base_lineage(snapshot)
    expected_audit = [
        (
            *expected_base,
            len(manifest.pages),
            manifest.observed_count,
            manifest.schema_sha256,
        )
    ]
    expected_page_lineage = [
        (
            page.page_index,
            page.result_offset,
            page.content_sha256,
            page.record_count,
        )
        for page in manifest.pages
    ]
    if audit != expected_audit or base_lineage != [expected_base]:
        raise SviStageLoadConflictError(
            "existing database represents a different manifest or lineage"
        )
    if page_lineage != expected_page_lineage:
        raise SviStageLoadConflictError(
            "existing database page lineage does not match its manifest"
        )
    if row_count != manifest.observed_count:
        raise SviStageLoadConflictError(
            "existing database row count does not match its manifest"
        )
    return row_count


def _load_database(path: Path, snapshot: ReconciledSviSnapshot) -> None:
    raw_columns_sql = ",\n".join(f"{_quoted(name)} varchar" for name in REQUIRED_FIELDS)
    insert_columns = (*REQUIRED_FIELDS, *LINEAGE_COLUMNS)
    insert_sql = (
        f"insert into {RAW_SCHEMA}.{RAW_TABLE} "
        f"({', '.join(_quoted(name) for name in insert_columns)}) "
        f"values ({', '.join('?' for _ in insert_columns)})"
    )
    manifest = snapshot.manifest
    connection = duckdb.connect(str(path))
    try:
        connection.execute(f"create schema {RAW_SCHEMA}")
        connection.execute(
            f"""
            create table {RAW_SCHEMA}.{RAW_TABLE} (
                {raw_columns_sql},
                source_id varchar not null,
                source_manifest_run_id varchar not null,
                source_snapshot_sha256 varchar not null,
                source_retrieved_at_utc varchar not null,
                source_modified_at varchar,
                source_page_index bigint not null,
                source_page_offset bigint not null,
                source_page_sha256 varchar not null
            )
            """
        )
        connection.execute(
            f"""
            create table {RAW_SCHEMA}.{AUDIT_TABLE} (
                source_id varchar not null,
                source_manifest_run_id varchar not null,
                snapshot_sha256 varchar not null,
                source_retrieved_at_utc varchar not null,
                source_modified_at varchar,
                page_count bigint not null,
                row_count bigint not null,
                schema_sha256 varchar not null
            )
            """
        )
        base_lineage = _base_lineage(snapshot)
        loaded_rows = 0
        for page in snapshot.pages:
            page_lineage = (
                page.manifest.page_index,
                page.manifest.result_offset,
                page.manifest.content_sha256,
            )
            batch = [
                tuple(_raw_text(row[field], field=field) for field in REQUIRED_FIELDS)
                + base_lineage
                + page_lineage
                for row in page.rows
            ]
            connection.executemany(insert_sql, batch)
            loaded_rows += len(batch)
        if loaded_rows != manifest.observed_count:
            raise SviStageLoadError(
                "loaded row count does not match the verified SVI manifest: "
                f"{loaded_rows} != {manifest.observed_count}"
            )
        connection.execute(
            f"insert into {RAW_SCHEMA}.{AUDIT_TABLE} values (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                *base_lineage,
                len(manifest.pages),
                loaded_rows,
                manifest.schema_sha256,
            ],
        )
        connection.execute("checkpoint")
    finally:
        connection.close()


def load_cdc_svi_county_2022_snapshot(
    manifest_path: Path,
    raw_root: Path,
    database_path: Path,
) -> SviStageLoadResult:
    """Verify and atomically load one immutable SVI snapshot into DuckDB."""
    try:
        snapshot = load_and_reconcile_svi_snapshot(manifest_path, raw_root)
    except (SviExtractionError, OSError, ValueError) as error:
        raise SviStageLoadError(
            f"SVI snapshot integrity validation failed: {error}"
        ) from error

    final_database = database_path.resolve()
    if final_database.exists():
        row_count = _verify_existing_database(final_database, snapshot)
        return SviStageLoadResult(
            status="database_noop",
            database_path=final_database,
            manifest_path=snapshot.manifest_path,
            page_paths=tuple(page.path for page in snapshot.pages),
            page_count=len(snapshot.pages),
            row_count=row_count,
            snapshot_sha256=snapshot.manifest.snapshot_sha256,
            database_noop=True,
        )

    final_database.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = final_database.with_name(
        f".{final_database.name}.{snapshot.manifest.pipeline_run_id}.partial"
    )
    if temporary_path.exists():
        raise SviStageLoadConflictError(
            f"database staging path already exists: {temporary_path}"
        )
    try:
        _load_database(temporary_path, snapshot)
        try:
            os.link(temporary_path, final_database)
        except FileExistsError as error:
            raise SviStageLoadConflictError(
                f"database path appeared concurrently: {final_database}"
            ) from error
    except SviStageLoadError:
        raise
    except (duckdb.Error, OSError) as error:
        raise SviStageLoadError(f"SVI raw load failed: {error}") from error
    finally:
        temporary_path.unlink(missing_ok=True)
        Path(f"{temporary_path}.wal").unlink(missing_ok=True)

    return SviStageLoadResult(
        status="loaded",
        database_path=final_database,
        manifest_path=snapshot.manifest_path,
        page_paths=tuple(page.path for page in snapshot.pages),
        page_count=len(snapshot.pages),
        row_count=snapshot.manifest.observed_count,
        snapshot_sha256=snapshot.manifest.snapshot_sha256,
        database_noop=False,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and load one local SVI raw snapshot into DuckDB."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the network-free SVI snapshot loader command."""
    arguments = _parser().parse_args(argv)
    result = load_cdc_svi_county_2022_snapshot(
        manifest_path=arguments.manifest,
        raw_root=arguments.raw_root,
        database_path=arguments.database,
    )
    print(
        json.dumps(
            {
                "database_noop": result.database_noop,
                "database_path": str(result.database_path),
                "manifest_path": str(result.manifest_path),
                "page_count": result.page_count,
                "page_paths": [str(path) for path in result.page_paths],
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
