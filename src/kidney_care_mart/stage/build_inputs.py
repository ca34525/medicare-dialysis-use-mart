"""Atomically assemble verified CMS, SVI, and facility snapshots in DuckDB."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import duckdb

from kidney_care_mart.contracts.cdc_svi_county_2022 import (
    CONTRACT_VERSION as SVI_CONTRACT_VERSION,
)
from kidney_care_mart.contracts.cms_dialysis_facility import (
    CONTRACT_VERSION as FACILITY_CONTRACT_VERSION,
)
from kidney_care_mart.contracts.cms_om_gv import (
    CONTRACT_VERSION as CMS_CONTRACT_VERSION,
)
from kidney_care_mart.extract.manifest import canonical_json_bytes, validate_run_id
from kidney_care_mart.stage.cdc_svi_county_2022 import (
    SviStageLoadError,
    load_cdc_svi_county_2022_snapshot,
)
from kidney_care_mart.stage.cms_dialysis_facility import (
    FacilityStageLoadError,
    load_cms_dialysis_facility_snapshot,
)
from kidney_care_mart.stage.cms_om_gv import (
    StageLoadError,
    load_cms_om_gv_snapshot,
)

LEGACY_BUILD_FORMAT_VERSION: Final = 1
CURRENT_BUILD_FORMAT_VERSION: Final = 2
RAW_SCHEMA: Final = "raw"
AUDIT_TABLE: Final = "build_input_audit"


class BuildInputError(RuntimeError):
    """The requested source set cannot produce a valid combined input."""


class BuildInputConflictError(BuildInputError):
    """An existing path or partial build represents different inputs."""


@dataclass(frozen=True, slots=True)
class SourceAudit:
    """Canonical source lineage used to identify a combined input set."""

    source_id: str
    manifest_run_id: str
    contract_version: str
    snapshot_sha256: str
    retrieved_at_utc: str
    row_count: int
    page_count: int

    def hash_payload(self) -> dict[str, object]:
        """Return the stable subset defining source content and contract."""
        return {
            "contract_version": self.contract_version,
            "manifest_run_id": self.manifest_run_id,
            "page_count": self.page_count,
            "row_count": self.row_count,
            "snapshot_sha256": self.snapshot_sha256,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class BuildInputResult:
    """Deterministic evidence for one combined input database."""

    status: str
    database_path: Path
    build_id: str
    input_set_sha256: str
    cms_row_count: int
    svi_row_count: int
    facility_row_count: int | None
    database_noop: bool


def _cms_declared_contract(manifest_path: Path) -> str | None:
    """Read only enough canonical CMS evidence to give v1 a clear error."""
    try:
        content = manifest_path.read_bytes()
        payload = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != content:
        return None
    schema = payload.get("schema")
    if not isinstance(schema, dict):
        return None
    version = schema.get("contract_version")
    return version if isinstance(version, str) else None


def _source_audits(
    cms_database: Path,
    svi_database: Path,
    facility_database: Path | None = None,
) -> tuple[SourceAudit, ...]:
    with duckdb.connect(str(cms_database), read_only=True) as connection:
        cms_row = connection.execute(
            """
            select source_id,
                   source_manifest_run_id,
                   content_sha256,
                   source_retrieved_at_utc,
                   row_count
            from raw.cms_om_gv_load_audit
            """
        ).fetchone()
    with duckdb.connect(str(svi_database), read_only=True) as connection:
        svi_row = connection.execute(
            """
            select source_id,
                   source_manifest_run_id,
                   snapshot_sha256,
                   source_retrieved_at_utc,
                   row_count,
                   page_count
            from raw.cdc_svi_county_2022_load_audit
            """
        ).fetchone()
    if cms_row is None or svi_row is None:
        raise BuildInputError("source load audit is missing")
    cms = SourceAudit(
        source_id=cms_row[0],
        manifest_run_id=cms_row[1],
        contract_version=CMS_CONTRACT_VERSION,
        snapshot_sha256=cms_row[2],
        retrieved_at_utc=cms_row[3],
        row_count=cms_row[4],
        page_count=1,
    )
    svi = SourceAudit(
        source_id=svi_row[0],
        manifest_run_id=svi_row[1],
        contract_version=SVI_CONTRACT_VERSION,
        snapshot_sha256=svi_row[2],
        retrieved_at_utc=svi_row[3],
        row_count=svi_row[4],
        page_count=svi_row[5],
    )
    if facility_database is None:
        return cms, svi
    with duckdb.connect(str(facility_database), read_only=True) as connection:
        facility_row = connection.execute(
            """
            select source_id,
                   source_manifest_run_id,
                   source_snapshot_sha256,
                   source_retrieved_at_utc,
                   row_count,
                   page_count
            from raw.cms_dialysis_facility_load_audit
            """
        ).fetchone()
    if facility_row is None:
        raise BuildInputError("facility source load audit is missing")
    facility = SourceAudit(
        source_id=facility_row[0],
        manifest_run_id=facility_row[1],
        contract_version=FACILITY_CONTRACT_VERSION,
        snapshot_sha256=facility_row[2],
        retrieved_at_utc=facility_row[3],
        row_count=facility_row[4],
        page_count=facility_row[5],
    )
    return cms, svi, facility


def _input_set_sha256(audits: tuple[SourceAudit, ...]) -> str:
    ordered = sorted(audits, key=lambda item: item.source_id)
    build_format_version = (
        CURRENT_BUILD_FORMAT_VERSION
        if len(audits) == 3
        else LEGACY_BUILD_FORMAT_VERSION
    )
    payload = {
        "build_format_version": build_format_version,
        "sources": [item.hash_payload() for item in ordered],
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _sql_string(value: str) -> str:
    """Quote a trusted local path as a DuckDB string literal."""
    return "'" + value.replace("'", "''") + "'"


def _verify_existing_database(
    database_path: Path,
    *,
    build_id: str,
    input_set_sha256: str,
    cms: SourceAudit,
    svi: SourceAudit,
    facility: SourceAudit | None,
) -> None:
    try:
        with duckdb.connect(str(database_path), read_only=True) as connection:
            if facility is None:
                audit = connection.execute(
                    """
                    select build_id,
                           input_set_sha256,
                           cms_manifest_run_id,
                           cms_content_sha256,
                           cms_row_count,
                           svi_manifest_run_id,
                           svi_snapshot_sha256,
                           svi_page_count,
                           svi_row_count
                    from raw.build_input_audit
                    """
                ).fetchall()
                counts = connection.execute(
                    """
                    select
                        (select count(*) from raw.cms_om_gv),
                        (select count(*) from raw.cdc_svi_county_2022)
                    """
                ).fetchone()
            else:
                audit = connection.execute(
                    """
                    select build_id,
                           input_set_sha256,
                           cms_manifest_run_id,
                           cms_content_sha256,
                           cms_row_count,
                           svi_manifest_run_id,
                           svi_snapshot_sha256,
                           svi_page_count,
                           svi_row_count,
                           facility_manifest_run_id,
                           facility_snapshot_sha256,
                           facility_page_count,
                           facility_row_count
                    from raw.build_input_audit
                    """
                ).fetchall()
                counts = connection.execute(
                    """
                    select
                        (select count(*) from raw.cms_om_gv),
                        (select count(*) from raw.cdc_svi_county_2022),
                        (select count(*) from raw.cms_dialysis_facility)
                    """
                ).fetchone()
    except (duckdb.Error, OSError) as error:
        raise BuildInputConflictError(
            "existing database is not a valid combined build input"
        ) from error
    common_expected = (
        build_id,
        input_set_sha256,
        cms.manifest_run_id,
        cms.snapshot_sha256,
        cms.row_count,
        svi.manifest_run_id,
        svi.snapshot_sha256,
        svi.page_count,
        svi.row_count,
    )
    expected = [
        common_expected
        if facility is None
        else (
            *common_expected,
            facility.manifest_run_id,
            facility.snapshot_sha256,
            facility.page_count,
            facility.row_count,
        )
    ]
    expected_counts = (
        (cms.row_count, svi.row_count)
        if facility is None
        else (cms.row_count, svi.row_count, facility.row_count)
    )
    if audit != expected or counts != expected_counts:
        raise BuildInputConflictError(
            "existing database represents a different build or inputs"
        )


def _copy_verified_sources(
    path: Path,
    *,
    build_id: str,
    input_set_sha256: str,
    cms_database: Path,
    svi_database: Path,
    facility_database: Path | None,
    cms: SourceAudit,
    svi: SourceAudit,
    facility: SourceAudit | None,
) -> None:
    connection = duckdb.connect(str(path))
    try:
        connection.execute(f"create schema {RAW_SCHEMA}")
        connection.execute(
            f"attach {_sql_string(str(cms_database))} as cms_input (read_only)"
        )
        connection.execute(
            f"attach {_sql_string(str(svi_database))} as svi_input (read_only)"
        )
        if facility_database is not None:
            connection.execute(
                f"attach {_sql_string(str(facility_database))} "
                "as facility_input (read_only)"
            )
        connection.execute(
            "create table raw.cms_om_gv as select * from cms_input.raw.cms_om_gv"
        )
        connection.execute(
            """
            create table raw.cms_om_gv_load_audit as
            select * from cms_input.raw.cms_om_gv_load_audit
            """
        )
        connection.execute(
            """
            create table raw.cdc_svi_county_2022 as
            select * from svi_input.raw.cdc_svi_county_2022
            """
        )
        connection.execute(
            """
            create table raw.cdc_svi_county_2022_load_audit as
            select * from svi_input.raw.cdc_svi_county_2022_load_audit
            """
        )
        if facility_database is not None:
            connection.execute(
                """
                create table raw.cms_dialysis_facility as
                select * from facility_input.raw.cms_dialysis_facility
                """
            )
            connection.execute(
                """
                create table raw.cms_dialysis_facility_load_audit as
                select * from facility_input.raw.cms_dialysis_facility_load_audit
                """
            )
        facility_audit_columns = (
            """
                , facility_source_id varchar
                , facility_manifest_run_id varchar
                , facility_contract_version varchar
                , facility_snapshot_sha256 varchar
                , facility_retrieved_at_utc varchar
                , facility_page_count bigint
                , facility_row_count bigint
            """
            if facility is not None
            else ""
        )
        connection.execute(
            f"""
            create table raw.build_input_audit (
                build_format_version integer not null,
                build_id varchar not null,
                input_set_sha256 varchar not null,
                cms_source_id varchar not null,
                cms_manifest_run_id varchar not null,
                cms_contract_version varchar not null,
                cms_content_sha256 varchar not null,
                cms_retrieved_at_utc varchar not null,
                cms_page_count bigint not null,
                cms_row_count bigint not null,
                svi_source_id varchar not null,
                svi_manifest_run_id varchar not null,
                svi_contract_version varchar not null,
                svi_snapshot_sha256 varchar not null,
                svi_retrieved_at_utc varchar not null,
                svi_page_count bigint not null,
                svi_row_count bigint not null
                {facility_audit_columns}
            )
            """
        )
        common_audit_values = [
            CURRENT_BUILD_FORMAT_VERSION
            if facility is not None
            else LEGACY_BUILD_FORMAT_VERSION,
            build_id,
            input_set_sha256,
            cms.source_id,
            cms.manifest_run_id,
            cms.contract_version,
            cms.snapshot_sha256,
            cms.retrieved_at_utc,
            cms.page_count,
            cms.row_count,
            svi.source_id,
            svi.manifest_run_id,
            svi.contract_version,
            svi.snapshot_sha256,
            svi.retrieved_at_utc,
            svi.page_count,
            svi.row_count,
        ]
        if facility is None:
            connection.execute(
                "insert into raw.build_input_audit values "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                common_audit_values,
            )
        else:
            connection.execute(
                """
                insert into raw.build_input_audit values (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?
                )
                """,
                [
                    *common_audit_values,
                    facility.source_id,
                    facility.manifest_run_id,
                    facility.contract_version,
                    facility.snapshot_sha256,
                    facility.retrieved_at_utc,
                    facility.page_count,
                    facility.row_count,
                ],
            )
        facility_count_sql = (
            "(select count(*) from raw.cms_dialysis_facility)"
            if facility is not None
            else "null::bigint"
        )
        counts = connection.execute(
            f"""
            select
                (select count(*) from raw.cms_om_gv),
                (select count(*) from raw.cdc_svi_county_2022),
                {facility_count_sql},
                (select count(*) from raw.build_input_audit)
            """
        ).fetchone()
        expected_counts = (
            cms.row_count,
            svi.row_count,
            facility.row_count if facility else None,
            1,
        )
        if counts != expected_counts:
            raise BuildInputError("combined raw relations do not reconcile")
        connection.execute("detach cms_input")
        connection.execute("detach svi_input")
        if facility_database is not None:
            connection.execute("detach facility_input")
        connection.execute("checkpoint")
    finally:
        connection.close()


def build_input_database(
    *,
    build_id: str,
    cms_manifest_path: Path,
    svi_manifest_path: Path,
    facility_manifest_path: Path | None = None,
    raw_root: Path,
    database_path: Path,
) -> BuildInputResult:
    """Verify immutable sources and atomically publish one input database.

    ``facility_manifest_path`` remains optional only for rebuilding completed
    pre-Plan-009 fixture paths. The CLI and current canonical build require it.
    """
    try:
        validate_run_id(build_id)
    except ValueError as error:
        raise BuildInputError(f"invalid build ID: {error}") from error
    if _cms_declared_contract(cms_manifest_path) == "cms_om_gv.raw.v1":
        raise BuildInputError(
            "cms_contract_upgrade_required: Plan 006 requires cms_om_gv.raw.v2"
        )

    final_database = database_path.resolve()
    final_database.parent.mkdir(parents=True, exist_ok=True)
    working_directory = final_database.with_name(
        f".{final_database.name}.{build_id}.inputs"
    )
    temporary_database = final_database.with_name(
        f".{final_database.name}.{build_id}.partial"
    )
    if working_directory.exists() or temporary_database.exists():
        raise BuildInputConflictError("combined build staging path already exists")
    working_directory.mkdir()
    cms_database = working_directory / "cms.duckdb"
    svi_database = working_directory / "svi.duckdb"
    facility_database = (
        working_directory / "facility.duckdb"
        if facility_manifest_path is not None
        else None
    )
    try:
        try:
            load_cms_om_gv_snapshot(
                cms_manifest_path,
                raw_root,
                cms_database,
            )
        except StageLoadError as error:
            raise BuildInputError(f"CMS input verification failed: {error}") from error
        try:
            load_cdc_svi_county_2022_snapshot(
                svi_manifest_path,
                raw_root,
                svi_database,
            )
        except SviStageLoadError as error:
            raise BuildInputError(f"SVI input verification failed: {error}") from error

        if facility_manifest_path is not None and facility_database is not None:
            try:
                load_cms_dialysis_facility_snapshot(
                    facility_manifest_path,
                    raw_root,
                    facility_database,
                )
            except FacilityStageLoadError as error:
                raise BuildInputError(
                    f"facility input verification failed: {error}"
                ) from error

        audits = _source_audits(cms_database, svi_database, facility_database)
        cms, svi = audits[0], audits[1]
        facility = audits[2] if len(audits) == 3 else None
        input_set_sha256 = _input_set_sha256(audits)
        if final_database.exists():
            _verify_existing_database(
                final_database,
                build_id=build_id,
                input_set_sha256=input_set_sha256,
                cms=cms,
                svi=svi,
                facility=facility,
            )
            return BuildInputResult(
                status="database_noop",
                database_path=final_database,
                build_id=build_id,
                input_set_sha256=input_set_sha256,
                cms_row_count=cms.row_count,
                svi_row_count=svi.row_count,
                facility_row_count=facility.row_count if facility else None,
                database_noop=True,
            )

        _copy_verified_sources(
            temporary_database,
            build_id=build_id,
            input_set_sha256=input_set_sha256,
            cms_database=cms_database,
            svi_database=svi_database,
            facility_database=facility_database,
            cms=cms,
            svi=svi,
            facility=facility,
        )
        try:
            os.link(temporary_database, final_database)
        except FileExistsError as error:
            raise BuildInputConflictError(
                f"database path appeared concurrently: {final_database}"
            ) from error
    except BuildInputError:
        raise
    except (duckdb.Error, OSError) as error:
        raise BuildInputError(f"combined input build failed: {error}") from error
    finally:
        temporary_database.unlink(missing_ok=True)
        Path(f"{temporary_database}.wal").unlink(missing_ok=True)
        cms_database.unlink(missing_ok=True)
        Path(f"{cms_database}.wal").unlink(missing_ok=True)
        svi_database.unlink(missing_ok=True)
        Path(f"{svi_database}.wal").unlink(missing_ok=True)
        if facility_database is not None:
            facility_database.unlink(missing_ok=True)
            Path(f"{facility_database}.wal").unlink(missing_ok=True)
        working_directory.rmdir()

    return BuildInputResult(
        status="loaded",
        database_path=final_database,
        build_id=build_id,
        input_set_sha256=input_set_sha256,
        cms_row_count=cms.row_count,
        svi_row_count=svi.row_count,
        facility_row_count=facility.row_count if facility else None,
        database_noop=False,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify CMS v2, SVI, and facility manifests into one local DuckDB input."
        )
    )
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--cms-manifest", required=True, type=Path)
    parser.add_argument("--svi-manifest", required=True, type=Path)
    parser.add_argument("--facility-manifest", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--database", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    result = build_input_database(
        build_id=arguments.build_id,
        cms_manifest_path=arguments.cms_manifest,
        svi_manifest_path=arguments.svi_manifest,
        facility_manifest_path=arguments.facility_manifest,
        raw_root=arguments.raw_root,
        database_path=arguments.database,
    )
    print(
        json.dumps(
            {
                "build_id": result.build_id,
                "cms_row_count": result.cms_row_count,
                "database_noop": result.database_noop,
                "database_path": str(result.database_path),
                "facility_row_count": result.facility_row_count,
                "input_set_sha256": result.input_set_sha256,
                "status": result.status,
                "svi_row_count": result.svi_row_count,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
