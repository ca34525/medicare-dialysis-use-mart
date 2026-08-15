"""Network-free acceptance tests for Plan 006 dimensions and CMS facts."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Sequence
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
from kidney_care_mart.extract.manifest import canonical_json_bytes
from kidney_care_mart.stage.build_inputs import build_input_database

REPOSITORY_ROOT = Path(__file__).parents[2]
PROJECT_DIR = REPOSITORY_ROOT / "analytics"
CMS_FIXTURE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "cms_om_gv"
SVI_FIXTURE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "cdc_svi_county_2022"
PROFILE_EXAMPLE = PROJECT_DIR / "profiles.example.yml"

DIMENSIONAL_RELATIONS = (
    "staging.dim_year",
    "staging.dim_county",
    "staging.fct_medicare_county_year",
    "staging.fct_medicare_benchmark_year",
    "staging.audit_cms_svi_county_reconciliation",
)

CMS_DIMENSIONAL_CSV = b"""YEAR,BENE_GEO_LVL,BENE_GEO_DESC,BENE_GEO_CD,BENE_AGE_LVL,BENES_OM_CNT,MA_PRTCPTN_RATE,BENE_DUAL_PCT,BENES_OP_DLYS_CNT,BENES_OP_DLYS_PCT,OP_DLYS_VISITS_PER_1000_BENES,OP_DLYS_MDCR_STDZD_PYMT_PC,ACUTE_HOSP_READMSN_PCT,ER_VISITS_PER_1000_BENES,ADDITIVE_NOTE
2023,County,CT-Fairfield,09001,All,800,0.4,0.2,12,0.015,900,175,0.12,450,historical identity
2023,State,CT,09,All,500000,0.5,0.2,5000,0.01,800,170,0.13,460,state benchmark
2023,National,National,,All,26000000,0.5,0.15,190000,0.0073,950,185,0.17,570,national benchmark
2024,County,AL-Synthetic County A,01001,All,1000,0.5,0.1,20,0.02,1500,200,0.15,500,current county
2024,County,AK-Synthetic County B,02013,All,900,0.4,0.2,9,0.01,800,175,0.12,450,current county
2024,State,DC,11,All,70000,0.3,0.2,700,0.01,750,210,0.14,470,DC county equivalent and benchmark
2024,State,AL,01,All,750000,0.55,0.12,7500,0.01,1200,180,0.17,600,state benchmark
2024,State,AK,02,All,120000,0.45,0.11,900,0.0075,700,220,0.16,550,state benchmark
2024,National,National,,All,27000000,0.54,0.14,202500,0.0075,970,190,0.18,590,national benchmark
"""


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


class SviFixtureOpener:
    def __call__(self, request: Request, _timeout: float) -> FakeResponse:
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/1"):
            path = SVI_FIXTURE_DIR / "layer.json"
        elif query.get("returnCountOnly") == ["true"]:
            path = SVI_FIXTURE_DIR / "count.json"
        else:
            offset = int(query["resultOffset"][0])
            path = SVI_FIXTURE_DIR / "pages" / f"page-{offset:06d}.json"
        return FakeResponse(path.read_bytes())


def fixed_now() -> datetime:
    return datetime(2026, 8, 14, 20, 0, tzinfo=UTC)


def materialize_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    raw_root = tmp_path / "raw"
    payload = json.loads((CMS_FIXTURE_DIR / "staging-manifest.json").read_bytes())
    content_hash = hashlib.sha256(CMS_DIMENSIONAL_CSV).hexdigest()
    row_count = CMS_DIMENSIONAL_CSV.count(b"\n") - 1
    payload["pipeline"]["run_id"] = "cms-om-gv-dimensional-fixture-001"
    payload["content"].update(
        {
            "byte_count": len(CMS_DIMENSIONAL_CSV),
            "csv_row_count": row_count,
            "sha256": content_hash,
        }
    )
    payload["transport"]["record_count"] = row_count
    payload["storage"]["blob_path"] = f"blobs/sha256/{content_hash}.csv"
    cms_blob = raw_root / "blobs" / "sha256" / f"{content_hash}.csv"
    cms_blob.parent.mkdir(parents=True)
    cms_blob.write_bytes(CMS_DIMENSIONAL_CSV)
    cms_manifest = (
        raw_root / "manifests" / "cms_om_gv" / "cms-om-gv-dimensional-fixture-001.json"
    )
    cms_manifest.parent.mkdir(parents=True)
    cms_manifest.write_bytes(canonical_json_bytes(payload))

    svi = extract_cdc_svi_county_2022(
        run_id="cdc-svi-dimensional-fixture-001",
        output_root=raw_root,
        opener=SviFixtureOpener(),
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=fixed_now,
        page_size=2,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    return raw_root, cms_manifest, svi.manifest_path


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


def semantic_checksums(database_path: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    with duckdb.connect(str(database_path)) as connection:
        for relation in DIMENSIONAL_RELATIONS:
            cursor = connection.execute(f"select * from {relation} order by all")
            columns = [item[0] for item in cursor.description]
            rows = [
                [str(value) if isinstance(value, Decimal) else value for value in row]
                for row in cursor.fetchall()
            ]
            content = json.dumps(
                {"columns": columns, "rows": rows},
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
            checksums[relation] = hashlib.sha256(content).hexdigest()
    return checksums


def build_database(tmp_path: Path, database_name: str) -> tuple[Path, Path]:
    raw_root, cms_manifest, svi_manifest = materialize_inputs(tmp_path)
    database_path = tmp_path / database_name
    build_input_database(
        build_id="plan-006-dimensional-fixture-001",
        cms_manifest_path=cms_manifest,
        svi_manifest_path=svi_manifest,
        raw_root=raw_root,
        database_path=database_path,
    )
    return database_path, profiles_dir(tmp_path)


def test_dimensions_facts_and_current_reconciliation_are_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, profile_dir = build_database(tmp_path, "first.duckdb")
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    first = invoke_dbt("build", profile_dir)

    assert first.success, first.exception
    docs = invoke_dbt(("docs", "generate"), profile_dir)
    assert docs.success, docs.exception
    with duckdb.connect(str(database_path)) as connection:
        counts = connection.execute(
            """
            select
                (select count(*) from staging.dim_year),
                (select count(*) from staging.dim_county),
                (select count(*) from staging.fct_medicare_county_year),
                (select count(*) from staging.fct_medicare_benchmark_year),
                (select count(*) from staging.audit_cms_svi_county_reconciliation)
            """
        ).fetchone()
        years = connection.execute(
            "select year, is_latest_cms_year from staging.dim_year order by year"
        ).fetchall()
        historical = connection.execute(
            """
            select geography_status,
                   is_current_county,
                   observed_cms_start_year,
                   observed_cms_end_year,
                   boundary_discontinuity_warning
            from staging.dim_county
            where county_fips = '09001'
            """
        ).fetchone()
        county_fact = connection.execute(
            """
            select benes_om_cnt,
                   benes_op_dlys_cnt,
                   benes_op_dlys_pct,
                   county_geography_mapping_method
            from staging.fct_medicare_county_year
            where county_fips = '11001' and year = 2024
            """
        ).fetchone()
        benchmark = connection.execute(
            """
            select benes_op_dlys_cnt, benes_op_dlys_pct
            from staging.fct_medicare_benchmark_year
            where benchmark_geography_type = 'national'
              and benchmark_geography_key = 'US'
              and year = 2024
            """
        ).fetchone()
        reconciliation = connection.execute(
            """
            select county_fips,
                   reconciliation_status,
                   cms_row_count,
                   svi_row_count,
                   cms_latest_year,
                   svi_vintage,
                   length(cms_source_content_sha256),
                   length(svi_source_snapshot_sha256)
            from staging.audit_cms_svi_county_reconciliation
            order by county_fips
            """
        ).fetchall()

    assert counts == (2, 14, 4, 6, 3)
    assert years == [(2023, False), (2024, True)]
    assert historical[:4] == ("historical_source_only", False, 2014, 2021)
    assert "No successor allocation" in historical[4]
    assert county_fact == (
        70000,
        700,
        Decimal("0.0100000000"),
        "district_of_columbia_state_to_county_equivalent",
    )
    assert benchmark == (202500, Decimal("0.0075000000"))
    assert reconciliation == [
        ("01001", "matched", 1, 1, 2024, 2022, 64, 64),
        ("02013", "matched", 1, 1, 2024, 2022, 64, 64),
        ("11001", "matched", 1, 1, 2024, 2022, 64, 64),
    ]
    first_checksums = semantic_checksums(database_path)

    second_path = tmp_path / "second.duckdb"
    raw_root = tmp_path / "raw"
    build_input_database(
        build_id="plan-006-dimensional-fixture-001",
        cms_manifest_path=(
            raw_root
            / "manifests"
            / "cms_om_gv"
            / "cms-om-gv-dimensional-fixture-001.json"
        ),
        svi_manifest_path=(
            raw_root
            / "manifests"
            / "cdc_svi_county_2022"
            / "cdc-svi-dimensional-fixture-001.json"
        ),
        raw_root=raw_root,
        database_path=second_path,
    )
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(second_path))
    second = invoke_dbt("build", profile_dir)

    assert second.success, second.exception
    assert semantic_checksums(second_path) == first_checksums


@pytest.mark.parametrize(
    ("case", "mutation", "expected_failure"),
    [
        (
            "dialysis-count-exceeds-beneficiaries",
            """
            update raw.cms_om_gv
            set "BENES_OP_DLYS_CNT" = '1001'
            where "BENE_GEO_CD" = '01001' and "BENE_AGE_LVL" = 'All'
            """,
            "assert_cms_dialysis_users_not_above_beneficiaries",
        ),
        (
            "latest-current-mismatch",
            """
            delete from raw.cms_om_gv
            where "BENE_GEO_CD" = '02013' and "BENE_AGE_LVL" = 'All'
            """,
            "assert_cms_svi_latest_current_reconciled",
        ),
        (
            "unexpected-county",
            """
            update raw.cms_om_gv
            set "BENE_GEO_CD" = '99999'
            where "BENE_GEO_CD" = '02013' and "BENE_AGE_LVL" = 'All'
            """,
            "assert_cms_county_fact_geography_resolves",
        ),
    ],
)
def test_dimensional_quality_failures_block_with_named_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    mutation: str,
    expected_failure: str,
) -> None:
    database_path, profile_dir = build_database(tmp_path, f"{case}.duckdb")
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(mutation)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    result = invoke_dbt("build", profile_dir)

    assert not result.success
    assert expected_failure in result_failures(result)
