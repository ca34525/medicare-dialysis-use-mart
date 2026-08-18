"""Network-free DuckDB/dbt acceptance tests for the SVI source-to-fact path."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import duckdb
import pytest
from dbt.adapters.factory import reset_adapters
from dbt.cli.main import dbtRunner, dbtRunnerResult

from kidney_care_mart.extract.cdc_svi_county_2022 import (
    extract_cdc_svi_county_2022,
)
from kidney_care_mart.extract.http import RetryPolicy
from kidney_care_mart.stage.cdc_svi_county_2022 import (
    load_cdc_svi_county_2022_snapshot,
)
from kidney_care_mart.stage.cms_om_gv import load_cms_om_gv_snapshot

REPOSITORY_ROOT = Path(__file__).parents[2]
PROJECT_DIR = REPOSITORY_ROOT / "analytics"
SVI_FIXTURE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "cdc_svi_county_2022"
CMS_FIXTURE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "cms_om_gv"
PROFILE_EXAMPLE = PROJECT_DIR / "profiles.example.yml"
STAGE_RELATION = "staging.stg_cdc_svi_county_2022"
DIMENSION_RELATION = "staging.dim_county"
FACT_RELATION = "staging.fct_svi_county"
METRIC_PREFIXES = (
    "rpl_themes",
    "rpl_theme1",
    "rpl_theme2",
    "rpl_theme3",
    "rpl_theme4",
    "ep_pov150",
    "ep_uninsur",
    "ep_age65",
    "ep_disabl",
    "ep_limeng",
    "ep_noveh",
)


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._stream = io.BytesIO(content)
        self.headers = {"Content-Length": str(len(content))}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


class FixtureOpener:
    def __init__(
        self,
        mutate_pages: Callable[[list[dict[str, object]]], None] | None = None,
    ) -> None:
        self.pages = [
            json.loads(
                (SVI_FIXTURE_DIR / "pages" / f"page-{offset:06d}.json").read_bytes()
            )
            for offset in (0, 2)
        ]
        if mutate_pages is not None:
            mutate_pages(self.pages)

    def __call__(self, request: Request, _timeout: float) -> FakeResponse:
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/1"):
            content = (SVI_FIXTURE_DIR / "layer.json").read_bytes()
        elif query.get("returnCountOnly") == ["true"]:
            content = (SVI_FIXTURE_DIR / "count.json").read_bytes()
        else:
            offset = int(query["resultOffset"][0])
            content = json.dumps(
                self.pages[offset // 2],
                separators=(",", ":"),
            ).encode("utf-8")
        return FakeResponse(content)


def fixed_now() -> datetime:
    return datetime(2026, 8, 14, 20, 0, tzinfo=UTC)


def materialize_svi_database(
    tmp_path: Path,
    *,
    run_id: str = "cdc-svi-dbt-fixture-001",
    mutate_pages: Callable[[list[dict[str, object]]], None] | None = None,
) -> Path:
    raw_root = tmp_path / f"raw-{run_id}"
    extraction = extract_cdc_svi_county_2022(
        run_id=run_id,
        output_root=raw_root,
        opener=FixtureOpener(mutate_pages),
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=fixed_now,
        page_size=2,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    database_path = tmp_path / f"{run_id}.duckdb"
    load_cdc_svi_county_2022_snapshot(
        extraction.manifest_path,
        raw_root,
        database_path,
    )
    return database_path


def add_cms_fixture_to_database(tmp_path: Path, database_path: Path) -> None:
    cms_raw_root = tmp_path / "cms-raw"
    cms_manifest = CMS_FIXTURE_DIR / "staging-manifest.json"
    payload = json.loads(cms_manifest.read_bytes())
    cms_blob = cms_raw_root.joinpath(*payload["storage"]["blob_path"].split("/"))
    cms_blob.parent.mkdir(parents=True)
    cms_blob.write_bytes((CMS_FIXTURE_DIR / "staging.csv").read_bytes())
    cms_manifest_path = (
        cms_raw_root
        / "manifests"
        / "cms_om_gv"
        / f"{payload['pipeline']['run_id']}.json"
    )
    cms_manifest_path.parent.mkdir(parents=True)
    cms_manifest_path.write_bytes(cms_manifest.read_bytes())
    cms_database = tmp_path / "cms-fixture.duckdb"
    load_cms_om_gv_snapshot(cms_manifest_path, cms_raw_root, cms_database)

    with duckdb.connect(str(database_path)) as connection:
        escaped_database = str(cms_database).replace("'", "''")
        connection.execute(f"attach '{escaped_database}' as cms_fixture (read_only)")
        connection.execute(
            """
            create table raw.cms_om_gv as
            select * replace (
                case
                    when "BENE_GEO_CD" = '01003' then '02013'
                    else "BENE_GEO_CD"
                end as "BENE_GEO_CD",
                case
                    when "BENE_GEO_CD" = '01003'
                        then 'AK-Synthetic County B'
                    else "BENE_GEO_DESC"
                end as "BENE_GEO_DESC"
            )
            from cms_fixture.raw.cms_om_gv
            where (
                "BENE_GEO_LVL" = 'County'
                and "BENE_AGE_LVL" = 'All'
                and "BENE_GEO_CD" in ('01001', '01003')
            ) or (
                "BENE_GEO_LVL" = 'State'
                and "BENE_AGE_LVL" = 'All'
                and "BENE_GEO_CD" in ('01', '11')
            ) or (
                "BENE_GEO_LVL" = 'National'
                and "BENE_AGE_LVL" = 'All'
            )
            """
        )
        connection.execute(
            """
            create table raw.cms_om_gv_load_audit as
            select * from cms_fixture.raw.cms_om_gv_load_audit
            """
        )
        connection.execute("detach cms_fixture")
        connection.execute(
            """
            create table raw.build_input_audit as
            select
                1::integer as build_format_version,
                'plan-005-combined-fixture-001'::varchar as build_id,
                repeat('d', 64)::varchar as input_set_sha256,
                cms.source_id::varchar as cms_source_id,
                cms.source_manifest_run_id::varchar as cms_manifest_run_id,
                'cms_om_gv.raw.v2'::varchar as cms_contract_version,
                cms.content_sha256::varchar as cms_content_sha256,
                cms.source_retrieved_at_utc::varchar as cms_retrieved_at_utc,
                1::bigint as cms_page_count,
                (select count(*) from raw.cms_om_gv)::bigint as cms_row_count,
                svi.source_id::varchar as svi_source_id,
                svi.source_manifest_run_id::varchar as svi_manifest_run_id,
                'cdc_svi_county_2022.raw.v1'::varchar as svi_contract_version,
                svi.snapshot_sha256::varchar as svi_snapshot_sha256,
                svi.source_retrieved_at_utc::varchar as svi_retrieved_at_utc,
                svi.page_count::bigint as svi_page_count,
                svi.row_count::bigint as svi_row_count
            from raw.cms_om_gv_load_audit as cms
            cross join raw.cdc_svi_county_2022_load_audit as svi
            """
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
    relations = (STAGE_RELATION, DIMENSION_RELATION, FACT_RELATION)
    payload: dict[str, object] = {}
    for relation in relations:
        cursor = connection.execute(f"select * from {relation} order by 1, 2")
        columns = [item[0] for item in cursor.description]
        rows = [
            [str(value) if isinstance(value, Decimal) else value for value in row]
            for row in cursor.fetchall()
        ]
        payload[relation] = {"columns": columns, "rows": rows}
    content = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(content).hexdigest()


def test_dbt_project_parses_with_svi_models(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(tmp_path / "parse.duckdb"))

    result = invoke_dbt("parse", profiles_dir(tmp_path))

    assert result.success, result.exception


def test_combined_fixture_build_types_svi_and_rebuilds_deterministically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = materialize_svi_database(tmp_path)
    add_cms_fixture_to_database(tmp_path, database_path)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))
    profile_dir = profiles_dir(tmp_path)

    first_build = invoke_dbt(
        ("build", "--exclude", "stg_cms_dialysis_facility+"), profile_dir
    )

    assert first_build.success, first_build.exception
    docs = invoke_dbt(("docs", "generate"), profile_dir)
    assert docs.success, docs.exception
    with duckdb.connect(str(database_path)) as connection:
        assert connection.execute(
            f"select count(*) from {STAGE_RELATION}"
        ).fetchone() == (3,)
        assert connection.execute(
            f"select count(*) from {DIMENSION_RELATION}"
        ).fetchone() == (14,)
        assert connection.execute(
            f"select count(*) from {FACT_RELATION}"
        ).fetchone() == (3,)
        assert connection.execute(
            f"""
            select county_fips
            from {DIMENSION_RELATION}
            where is_current_county
            order by county_fips
            """
        ).fetchall() == [("01001",), ("02013",), ("11001",)]
        first_checksum = semantic_checksum(connection)
        rows = {
            row[0]: row[1:]
            for row in connection.execute(
                f"""
                select county_fips,
                       {", ".join(f"{prefix}_raw, {prefix}, {prefix}_status" for prefix in METRIC_PREFIXES)}
                from {STAGE_RELATION}
                order by county_fips
                """
            ).fetchall()
        }

    assert rows["01001"][0:3] == ("0", 0, "reported")
    assert rows["01001"][3:6] == ("0.75", Decimal("0.75"), "reported")
    assert rows["11001"][3:6] == ("-999", None, "unavailable_sentinel")
    assert rows["02013"][21:24] == (None, None, "unavailable_null")
    assert rows["02013"][30:33] == ("-999", None, "unavailable_sentinel")

    second_build = invoke_dbt(
        ("build", "--exclude", "stg_cms_dialysis_facility+"), profile_dir
    )

    assert second_build.success, second_build.exception
    with duckdb.connect(str(database_path)) as connection:
        assert semantic_checksum(connection) == first_checksum


@pytest.mark.parametrize(
    ("case", "field", "value", "expected_failure"),
    [
        (
            "invalid-numeric",
            "RPL_THEMES",
            "BROKEN",
            "assert_svi_numeric_values_valid",
        ),
        (
            "rank-out-of-range",
            "RPL_THEMES",
            1.25,
            "assert_svi_rank_bounds",
        ),
        (
            "percentage-out-of-range",
            "EP_POV150",
            101,
            "assert_svi_percentage_bounds",
        ),
    ],
)
def test_svi_value_quality_failures_block_dbt_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    field: str,
    value: object,
    expected_failure: str,
) -> None:
    def mutate(pages: list[dict[str, object]]) -> None:
        pages[0]["features"][0]["attributes"][field] = value

    database_path = materialize_svi_database(
        tmp_path,
        run_id=f"cdc-svi-{case}",
        mutate_pages=mutate,
    )
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    result = invoke_dbt(
        ("build", "--select", "stg_cdc_svi_county_2022+"),
        profiles_dir(tmp_path),
    )

    assert not result.success
    assert expected_failure in result_failures(result)


@pytest.mark.parametrize(
    ("case", "sql", "expected_failure"),
    [
        (
            "duplicate-fips",
            """
            insert into raw.cdc_svi_county_2022
            select * replace ('02013' as "STCNTY")
            from raw.cdc_svi_county_2022
            where "STCNTY" = '01001'
            """,
            "assert_svi_county_fips_unique",
        ),
        (
            "invalid-fips",
            """
            update raw.cdc_svi_county_2022
            set "STCNTY" = 'ABCDE'
            where "STCNTY" = '01001'
            """,
            "assert_svi_county_fips_valid",
        ),
    ],
)
def test_svi_grain_quality_failures_block_dbt_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    sql: str,
    expected_failure: str,
) -> None:
    database_path = materialize_svi_database(tmp_path, run_id=f"cdc-svi-{case}")
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(sql)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    result = invoke_dbt(
        ("build", "--select", "stg_cdc_svi_county_2022+"),
        profiles_dir(tmp_path),
    )

    assert not result.success
    assert expected_failure in result_failures(result)
