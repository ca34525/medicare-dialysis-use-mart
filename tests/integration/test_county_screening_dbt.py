"""Network-free acceptance tests for Plan 007 county screening models."""

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
PINNED_RAW_ROOT = REPOSITORY_ROOT / "data" / "raw"
PINNED_CMS_MANIFEST = (
    PINNED_RAW_ROOT
    / "manifests"
    / "cms_om_gv"
    / "cms-om-gv-v2-live-20260815T015000Z.json"
)
PINNED_SVI_MANIFEST = (
    PINNED_RAW_ROOT
    / "manifests"
    / "cdc_svi_county_2022"
    / "cdc-svi-2022-live-20260814T194625Z.json"
)

SCREENING_RELATIONS = (
    "staging.int_county_screening_threshold",
    "staging.mart_county_screening",
    "staging.audit_screening_quadrant_summary",
)

CMS_SCREENING_CSV = b"""YEAR,BENE_GEO_LVL,BENE_GEO_DESC,BENE_GEO_CD,BENE_AGE_LVL,BENES_OM_CNT,MA_PRTCPTN_RATE,BENE_DUAL_PCT,BENES_OP_DLYS_CNT,BENES_OP_DLYS_PCT,OP_DLYS_VISITS_PER_1000_BENES,OP_DLYS_MDCR_STDZD_PYMT_PC,ACUTE_HOSP_READMSN_PCT,ER_VISITS_PER_1000_BENES,ADDITIVE_NOTE
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


def materialize_fixture_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    raw_root = tmp_path / "raw"
    payload = json.loads((CMS_FIXTURE_DIR / "staging-manifest.json").read_bytes())
    content_hash = hashlib.sha256(CMS_SCREENING_CSV).hexdigest()
    row_count = CMS_SCREENING_CSV.count(b"\n") - 1
    payload["pipeline"]["run_id"] = "cms-om-gv-screening-fixture-001"
    payload["content"].update(
        {
            "byte_count": len(CMS_SCREENING_CSV),
            "csv_row_count": row_count,
            "sha256": content_hash,
        }
    )
    payload["transport"]["record_count"] = row_count
    payload["storage"]["blob_path"] = f"blobs/sha256/{content_hash}.csv"
    cms_blob = raw_root / "blobs" / "sha256" / f"{content_hash}.csv"
    cms_blob.parent.mkdir(parents=True)
    cms_blob.write_bytes(CMS_SCREENING_CSV)
    cms_manifest = (
        raw_root / "manifests" / "cms_om_gv" / "cms-om-gv-screening-fixture-001.json"
    )
    cms_manifest.parent.mkdir(parents=True)
    cms_manifest.write_bytes(canonical_json_bytes(payload))

    svi = extract_cdc_svi_county_2022(
        run_id="cdc-svi-screening-fixture-001",
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
        for relation in SCREENING_RELATIONS:
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


def build_fixture_database(tmp_path: Path, database_name: str) -> tuple[Path, Path]:
    raw_root, cms_manifest, svi_manifest = materialize_fixture_inputs(tmp_path)
    database_path = tmp_path / database_name
    build_input_database(
        build_id="plan-007-screening-fixture-001",
        cms_manifest_path=cms_manifest,
        svi_manifest_path=svi_manifest,
        raw_root=raw_root,
        database_path=database_path,
    )
    return database_path, profiles_dir(tmp_path)


def assert_dbt_build(database_path: Path, profile_dir: Path) -> None:
    result = invoke_dbt("build", profile_dir)
    assert result.success, result.exception


def assert_pinned_screening_build(profile_dir: Path) -> None:
    seed = invoke_dbt("seed", profile_dir)
    assert seed.success, seed.exception
    models = invoke_dbt("run", profile_dir)
    assert models.success, models.exception
    tests = invoke_dbt(
        ("test", "--select", "int_county_screening_threshold+"),
        profile_dir,
    )
    assert tests.success, tests.exception


def test_screening_fixture_is_transparent_complete_and_deterministic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_path, profile_dir = build_fixture_database(tmp_path, "first.duckdb")
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(first_path))
    assert_dbt_build(first_path, profile_dir)
    docs = invoke_dbt(("docs", "generate"), profile_dir)
    assert docs.success, docs.exception

    with duckdb.connect(str(first_path)) as connection:
        threshold = connection.execute(
            """
            select screening_definition_version,
                   screening_run_id,
                   cms_year,
                   svi_vintage,
                   dialysis_use_p75_threshold,
                   current_county_count,
                   threshold_eligible_count,
                   threshold_excluded_count
            from staging.int_county_screening_threshold
            """
        ).fetchone()
        screening = connection.execute(
            """
            select county_fips,
                   is_higher_observed_dialysis_use,
                   is_higher_social_vulnerability,
                   screening_quadrant,
                   dialysis_use_p75_threshold
            from staging.mart_county_screening
            order by county_fips
            """
        ).fetchall()
        summary = connection.execute(
            """
            select screening_quadrant, screening_row_count
            from staging.audit_screening_quadrant_summary
            order by category_display_order
            """
        ).fetchall()
        columns = {
            row[0]
            for row in connection.execute(
                """
                select column_name
                from information_schema.columns
                where table_schema = 'staging'
                  and table_name = 'mart_county_screening'
                """
            ).fetchall()
        }

    assert threshold == (
        "county_screening.v1",
        "plan-007-screening-fixture-001",
        2024,
        2022,
        Decimal("0.0150000000"),
        3,
        3,
        0,
    )
    assert screening == [
        (
            "01001",
            True,
            False,
            "higher_use_lower_vulnerability",
            Decimal("0.0150000000"),
        ),
        (
            "02013",
            False,
            True,
            "lower_use_higher_vulnerability",
            Decimal("0.0150000000"),
        ),
        (
            "11001",
            False,
            True,
            "lower_use_higher_vulnerability",
            Decimal("0.0150000000"),
        ),
    ]
    assert summary == [
        ("higher_use_higher_vulnerability", 0),
        ("higher_use_lower_vulnerability", 1),
        ("lower_use_higher_vulnerability", 2),
        ("lower_use_lower_vulnerability", 0),
        ("insufficient_data", 0),
    ]
    assert not any(
        forbidden in column
        for column in columns
        for forbidden in ("score", "priority", "recommendation", "facility")
    )
    first_checksums = semantic_checksums(first_path)

    second_path = tmp_path / "second.duckdb"
    raw_root = tmp_path / "raw"
    build_input_database(
        build_id="plan-007-screening-fixture-001",
        cms_manifest_path=(
            raw_root
            / "manifests"
            / "cms_om_gv"
            / "cms-om-gv-screening-fixture-001.json"
        ),
        svi_manifest_path=(
            raw_root
            / "manifests"
            / "cdc_svi_county_2022"
            / "cdc-svi-screening-fixture-001.json"
        ),
        raw_root=raw_root,
        database_path=second_path,
    )
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(second_path))
    assert_dbt_build(second_path, profile_dir)

    assert semantic_checksums(second_path) == first_checksums


@pytest.mark.parametrize(
    ("case", "mutation", "expected_failure"),
    [
        (
            "duplicate-build-audit",
            "insert into raw.build_input_audit select * from raw.build_input_audit",
            "assert_build_input_audit_singleton",
        ),
        (
            "lineage-mismatch",
            """
            update raw.build_input_audit
            set cms_content_sha256 = repeat('d', 64)
            """,
            "assert_build_input_lineage_reconciles_facts",
        ),
        (
            "invalid-cms-component",
            """
            update raw.cms_om_gv
            set "BENES_OP_DLYS_PCT" = 'not-a-number'
            where "BENE_GEO_CD" = '01001'
              and "YEAR" = '2024'
              and "BENE_AGE_LVL" = 'All'
            """,
            "assert_cms_numeric_values_valid",
        ),
        (
            "latest-current-mismatch",
            """
            delete from raw.cms_om_gv
            where "BENE_GEO_CD" = '02013'
              and "YEAR" = '2024'
              and "BENE_AGE_LVL" = 'All'
            """,
            "assert_cms_svi_latest_current_reconciled",
        ),
    ],
)
def test_screening_quality_failures_block_with_named_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    mutation: str,
    expected_failure: str,
) -> None:
    database_path, profile_dir = build_fixture_database(tmp_path, f"{case}.duckdb")
    with duckdb.connect(str(database_path)) as connection:
        connection.execute(mutation)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    result = invoke_dbt("build", profile_dir)

    assert not result.success
    assert expected_failure in result_failures(result)


def test_materialized_screening_inconsistencies_fail_named_tests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path, profile_dir = build_fixture_database(
        tmp_path,
        "screening-state-failures.duckdb",
    )
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))
    assert_dbt_build(database_path, profile_dir)

    cases = (
        (
            """
            update staging.mart_county_screening
            set county_fips = '09001'
            where county_fips = '01001'
            """,
            "assert_screening_rows_current_and_reconciled",
            """
            update staging.mart_county_screening
            set county_fips = '01001'
            where county_fips = '09001'
            """,
        ),
        (
            """
            update staging.mart_county_screening
            set dialysis_use_p75_threshold = 0.99
            where county_fips = '01001'
            """,
            "assert_screening_national_threshold_fixed",
            """
            update staging.mart_county_screening
            set dialysis_use_p75_threshold = 0.015
            where county_fips = '01001'
            """,
        ),
        (
            """
            update staging.mart_county_screening
            set is_higher_observed_dialysis_use = false
            where county_fips = '01001'
            """,
            "assert_screening_classification_consistent",
            """
            update staging.mart_county_screening
            set is_higher_observed_dialysis_use = true
            where county_fips = '01001'
            """,
        ),
        (
            """
            update staging.audit_screening_quadrant_summary
            set screening_row_count = screening_row_count + 1
            where category_display_order = 1
            """,
            "assert_screening_summary_reconciles",
            """
            update staging.audit_screening_quadrant_summary
            set screening_row_count = screening_row_count - 1
            where category_display_order = 1
            """,
        ),
        (
            """
            update staging.int_county_screening_threshold
            set dialysis_use_p75_threshold = 1.1
            """,
            "assert_screening_threshold_valid",
            """
            update staging.int_county_screening_threshold
            set dialysis_use_p75_threshold = 0.015
            """,
        ),
    )

    for mutation, test_name, revert in cases:
        with duckdb.connect(str(database_path)) as connection:
            connection.execute(mutation)
        result = invoke_dbt(("test", "--select", test_name), profile_dir)
        assert not result.success
        assert test_name in result_failures(result)
        with duckdb.connect(str(database_path)) as connection:
            connection.execute(revert)

    with duckdb.connect(str(database_path)) as connection:
        connection.execute("drop view staging.dim_year")
        connection.execute(
            """
            create table staging.dim_year as
            select * from (
                values (2023, true), (2024, true)
            ) as years(year, is_latest_cms_year)
            """
        )
    result = invoke_dbt(
        ("test", "--select", "assert_screening_latest_year_singular"),
        profile_dir,
    )
    assert not result.success
    assert "assert_screening_latest_year_singular" in result_failures(result)


@pytest.mark.skipif(
    not PINNED_CMS_MANIFEST.exists() or not PINNED_SVI_MANIFEST.exists(),
    reason="ignored verified Plan 006 manifests are not present",
)
def test_pinned_plan_006_inputs_reproduce_screening_at_fresh_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_dir = profiles_dir(tmp_path)
    checksums: list[dict[str, str]] = []

    for database_name in ("pinned-first.duckdb", "pinned-second.duckdb"):
        database_path = tmp_path / database_name
        result = build_input_database(
            build_id="plan-007-pinned-screening-001",
            cms_manifest_path=PINNED_CMS_MANIFEST,
            svi_manifest_path=PINNED_SVI_MANIFEST,
            raw_root=PINNED_RAW_ROOT,
            database_path=database_path,
        )
        assert result.input_set_sha256 == (
            "6fb37a3834b2d9dba28395520e92d5f999cee3c88220b8a7c4054fae3bbc8307"
        )
        monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))
        assert_pinned_screening_build(profile_dir)

        with duckdb.connect(str(database_path)) as connection:
            threshold = connection.execute(
                """
                select current_county_count,
                       threshold_eligible_count,
                       threshold_excluded_count,
                       dialysis_use_p75_threshold
                from staging.int_county_screening_threshold
                """
            ).fetchone()
            summary = connection.execute(
                """
                select screening_quadrant, screening_row_count
                from staging.audit_screening_quadrant_summary
                order by category_display_order
                """
            ).fetchall()

        assert threshold == (3144, 2148, 996, Decimal("0.0086000000"))
        assert summary == [
            ("higher_use_higher_vulnerability", 354),
            ("higher_use_lower_vulnerability", 188),
            ("lower_use_higher_vulnerability", 259),
            ("lower_use_lower_vulnerability", 1347),
            ("insufficient_data", 996),
        ]
        checksums.append(semantic_checksums(database_path))

    assert checksums[1] == checksums[0]
