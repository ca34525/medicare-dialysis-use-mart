"""Fixture-sized dbt acceptance tests for typed facility models."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from dbt.adapters.factory import reset_adapters
from dbt.cli.main import dbtRunner, dbtRunnerResult

from kidney_care_mart.contracts.cms_dialysis_facility import REQUIRED_FIELDS
from kidney_care_mart.extract.cms_dialysis_facility import (
    CATALOG_URL,
    DATASTORE_SCHEMA_URL,
    extract_cms_dialysis_facility,
)
from kidney_care_mart.extract.http import RetryPolicy
from kidney_care_mart.stage.cms_dialysis_facility import (
    load_cms_dialysis_facility_snapshot,
)

ROOT = Path(__file__).parents[2]
PROJECT_DIR = ROOT / "analytics"
PROFILE_EXAMPLE = PROJECT_DIR / "profiles.example.yml"
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "cms_dialysis_facility"
CSV_PATH = FIXTURE_DIR / "staging.csv"
RELATIONS = (
    "staging.stg_cms_dialysis_facility",
    "staging.dim_facility",
    "staging.fct_facility_quality_snapshot",
)


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._stream = io.BytesIO(content)
        self.headers = {
            "Content-Length": str(len(content)),
            "Content-Type": "text/csv",
        }

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


def _api_payload() -> dict[str, object]:
    required = {field.csv_header: field for field in REQUIRED_FIELDS}
    with CSV_PATH.open(encoding="utf-8", newline="") as stream:
        header = next(csv.reader(stream))
    fields = {}
    for name in header:
        mapping = required.get(name)
        api_name = mapping.api_field_name if mapping else "synthetic_additive_note"
        fields[api_name] = {
            "type": "text",
            "mysql_type": "text",
            "description": name,
        }
    return {
        "results": [],
        "count": 3,
        "schema": {"fixture-resource-id": {"fields": fields}},
        "query": {"limit": 1, "offset": 0},
    }


def materialize_database(tmp_path: Path) -> Path:
    raw_root = tmp_path / "raw"
    catalog = json.loads((FIXTURE_DIR / "catalog.json").read_bytes())

    def json_loader(url: str) -> dict[str, object]:
        if url == CATALOG_URL:
            return catalog
        if url == DATASTORE_SCHEMA_URL:
            return _api_payload()
        raise AssertionError(f"unexpected fixture URL: {url}")

    extraction = extract_cms_dialysis_facility(
        run_id="facility-dbt-fixture-001",
        output_root=raw_root,
        json_loader=json_loader,
        opener=lambda _request, _timeout: FakeResponse(CSV_PATH.read_bytes()),
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        retry_policy=RetryPolicy(max_attempts=1),
    )
    database_path = tmp_path / "facility.duckdb"
    load_cms_dialysis_facility_snapshot(
        extraction.manifest_path,
        raw_root,
        database_path,
    )
    _add_combined_lineage_fixture(database_path)
    return database_path


def _add_combined_lineage_fixture(database_path: Path) -> None:
    """Add minimal non-facility parents for the cross-source lineage gate."""
    cms_sha256 = "a" * 64
    svi_sha256 = "b" * 64
    input_set_sha256 = "c" * 64
    retrieved_at = "2026-08-15T12:00:00Z"
    with duckdb.connect(str(database_path)) as connection:
        facility = connection.execute(
            """
            select source_id,
                   source_manifest_run_id,
                   source_snapshot_sha256,
                   source_retrieved_at_utc,
                   row_count
            from raw.cms_dialysis_facility_load_audit
            """
        ).fetchone()
        assert facility is not None
        connection.execute("create schema staging")
        connection.execute(
            """
            create table staging.fct_medicare_county_year as
            select 'cms_om_gv'::varchar as source_id,
                   'cms-fixture-001'::varchar as source_manifest_run_id,
                   ?::varchar as source_content_sha256,
                   ?::varchar as source_retrieved_at_utc
            """,
            [cms_sha256, retrieved_at],
        )
        connection.execute(
            """
            create table staging.fct_svi_county as
            select 'cdc_svi_county_2022'::varchar as source_id,
                   'svi-fixture-001'::varchar as source_manifest_run_id,
                   ?::varchar as source_snapshot_sha256,
                   ?::varchar as source_retrieved_at_utc
            """,
            [svi_sha256, retrieved_at],
        )
        connection.execute(
            """
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
                svi_row_count bigint not null,
                facility_source_id varchar,
                facility_manifest_run_id varchar,
                facility_contract_version varchar,
                facility_snapshot_sha256 varchar,
                facility_retrieved_at_utc varchar,
                facility_page_count bigint,
                facility_row_count bigint
            )
            """
        )
        connection.execute(
            """
            insert into raw.build_input_audit values (
                2, 'facility-dbt-fixture-001', ?,
                'cms_om_gv', 'cms-fixture-001', 'cms_om_gv.raw.v2', ?, ?, 1, 1,
                'cdc_svi_county_2022', 'svi-fixture-001',
                'cdc_svi_county_2022.raw.v1', ?, ?, 1, 1,
                ?, ?, 'cms_dialysis_facility.raw.v1', ?, ?, 1, ?
            )
            """,
            [
                input_set_sha256,
                cms_sha256,
                retrieved_at,
                svi_sha256,
                retrieved_at,
                facility[0],
                facility[1],
                facility[2],
                facility[3],
                facility[4],
            ],
        )


def profiles_dir(tmp_path: Path) -> Path:
    destination = tmp_path / "profiles"
    destination.mkdir(exist_ok=True)
    (destination / "profiles.yml").write_bytes(PROFILE_EXAMPLE.read_bytes())
    return destination


def invoke_dbt(command: str | Sequence[str], profile_dir: Path) -> dbtRunnerResult:
    arguments = [command] if isinstance(command, str) else list(command)
    try:
        return dbtRunner().invoke(
            [
                *arguments,
                "--project-dir",
                str(PROJECT_DIR),
                "--profiles-dir",
                str(profile_dir),
            ]
        )
    finally:
        reset_adapters()


def result_failures(result: dbtRunnerResult) -> tuple[str, ...]:
    execution = result.result
    if execution is None or not hasattr(execution, "results"):
        return ()
    return tuple(
        item.node.name
        for item in execution.results
        if str(item.status).lower() not in {"success", "pass", "skipped"}
    )


def semantic_checksum(connection: duckdb.DuckDBPyConnection) -> str:
    payload: dict[str, object] = {}
    for relation in RELATIONS:
        cursor = connection.execute(f"select * from {relation} order by all")
        columns = [item[0] for item in cursor.description]
        rows = [
            [
                str(value) if isinstance(value, (date, Decimal)) else value
                for value in row
            ]
            for row in cursor.fetchall()
        ]
        payload[relation] = {"columns": columns, "rows": rows}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_facility_models_type_available_values_and_preserve_unavailability(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = materialize_database(tmp_path)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))
    profile_dir = profiles_dir(tmp_path)

    first = invoke_dbt(
        (
            "build",
            "--select",
            "stg_cms_dialysis_facility+",
            "--indirect-selection",
            "cautious",
        ),
        profile_dir,
    )

    assert first.success, first.exception
    docs = invoke_dbt(("docs", "generate"), profile_dir)
    assert docs.success, docs.exception
    with duckdb.connect(str(database_path)) as connection:
        counts = tuple(
            connection.execute(f"select count(*) from {relation}").fetchone()[0]
            for relation in RELATIONS
        )
        reported = connection.execute(
            """
            select five_star_rating,
                   five_star_availability_status,
                   five_star_period_start,
                   five_star_period_end,
                   survival_denominator,
                   survival_estimate,
                   survival_lower_confidence_limit,
                   survival_upper_confidence_limit
            from staging.fct_facility_quality_snapshot
            where ccn = '012345'
            """
        ).fetchone()
        unavailable = connection.execute(
            """
            select five_star_rating_raw,
                   five_star_rating,
                   five_star_availability_code,
                   five_star_availability_status,
                   five_star_unavailability_reason
            from staging.stg_cms_dialysis_facility
            where ccn = '654321'
            """
        ).fetchone()
        dimension = connection.execute(
            """
            select ccn,
                   dialysis_stations,
                   chain_owned,
                   county_fips,
                   geography_match_status
            from staging.dim_facility
            where ccn = '123456'
            """
        ).fetchone()
        first_checksum = semantic_checksum(connection)

    assert counts == (3, 3, 3)
    assert reported == (
        4,
        "available",
        date(2021, 1, 1),
        date(2024, 12, 31),
        100,
        Decimal("10.5000000000"),
        Decimal("9.0000000000"),
        Decimal("12.0000000000"),
    )
    assert unavailable == ("0", None, "258", "not_available", "insufficient_history")
    assert dimension == ("123456", 0, False, None, "not_attempted")

    second = invoke_dbt(
        (
            "build",
            "--select",
            "stg_cms_dialysis_facility+",
            "--indirect-selection",
            "cautious",
        ),
        profile_dir,
    )
    assert second.success, second.exception
    with duckdb.connect(str(database_path)) as connection:
        assert semantic_checksum(connection) == first_checksum


@pytest.mark.parametrize(
    ("case", "mutation", "expected_failure"),
    (
        (
            "invalid-five-star",
            """update raw.cms_dialysis_facility set "Five Star" = '6'
               where "CMS Certification Number (CCN)" = '012345' """,
            "assert_facility_five_star_valid",
        ),
        (
            "missing-confidence-limit",
            """update raw.cms_dialysis_facility
               set "Hospitalization Rate: Upper Confidence Limit (97.5%)" = ''
               where "CMS Certification Number (CCN)" = '012345' """,
            "assert_facility_quality_companions_complete",
        ),
        (
            "reversed-confidence-interval",
            """update raw.cms_dialysis_facility
               set "Mortality Rate: Lower Confidence Limit (2.5%)" = '11.0'
               where "CMS Certification Number (CCN)" = '012345' """,
            "assert_facility_confidence_intervals_valid",
        ),
        (
            "reversed-period",
            """update raw.cms_dialysis_facility set "SMR Date" = '31Dec2024-01Jan2024'
               where "CMS Certification Number (CCN)" = '012345' """,
            "assert_facility_periods_valid",
        ),
        (
            "unknown-availability",
            """update raw.cms_dialysis_facility
               set "Patient Survival data availability code" = '999'
               where "CMS Certification Number (CCN)" = '012345' """,
            "assert_facility_availability_codes_valid",
        ),
    ),
)
def test_facility_quality_failures_block_named_dbt_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    mutation: str,
    expected_failure: str,
) -> None:
    database_path = materialize_database(tmp_path)
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(mutation)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    result = invoke_dbt(
        (
            "build",
            "--select",
            "stg_cms_dialysis_facility+",
            "--indirect-selection",
            "cautious",
        ),
        profiles_dir(tmp_path),
    )

    assert not result.success
    assert expected_failure in result_failures(result)
