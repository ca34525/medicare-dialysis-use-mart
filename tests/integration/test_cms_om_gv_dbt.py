"""Network-free DuckDB/dbt acceptance tests for CMS county staging."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest
from dbt.adapters.factory import reset_adapters
from dbt.cli.main import dbtRunner, dbtRunnerResult

from kidney_care_mart.extract.manifest import canonical_json_bytes
from kidney_care_mart.stage.cms_om_gv import load_cms_om_gv_snapshot

REPOSITORY_ROOT = Path(__file__).parents[2]
PROJECT_DIR = REPOSITORY_ROOT / "analytics"
FIXTURE_DIR = REPOSITORY_ROOT / "tests" / "fixtures" / "cms_om_gv"
FIXTURE_CSV = FIXTURE_DIR / "staging.csv"
FIXTURE_MANIFEST = FIXTURE_DIR / "staging-manifest.json"
PROFILE_EXAMPLE = PROJECT_DIR / "profiles.example.yml"
MODEL_RELATION = "staging.stg_cms_om_gv_county_year"
METRIC_PREFIXES = (
    "benes_om_cnt",
    "ma_prtcptn_rate",
    "bene_dual_pct",
    "benes_op_dlys_pct",
    "op_dlys_visits_per_1000_benes",
    "op_dlys_mdcr_stdzd_pymt_pc",
    "acute_hosp_readmsn_pct",
    "er_visits_per_1000_benes",
)
NA_RAW_VALUES = ("NA", "na", " NA ", "NA", "na", " NA ", "NA", "na")


def materialize_snapshot(
    tmp_path: Path,
    *,
    run_id: str = "cms-om-gv-staging-fixture-001",
    csv_bytes: bytes | None = None,
) -> tuple[Path, Path]:
    """Materialize canonical fixture bytes beneath a temporary raw root."""
    content = FIXTURE_CSV.read_bytes() if csv_bytes is None else csv_bytes
    payload = json.loads(FIXTURE_MANIFEST.read_bytes())
    content_hash = hashlib.sha256(content).hexdigest()
    row_count = content.count(b"\n") - 1
    payload["pipeline"]["run_id"] = run_id
    payload["content"].update(
        {
            "byte_count": len(content),
            "csv_row_count": row_count,
            "sha256": content_hash,
        }
    )
    payload["transport"]["record_count"] = row_count
    payload["storage"]["blob_path"] = f"blobs/sha256/{content_hash}.csv"
    raw_root = tmp_path / "raw"
    blob_path = raw_root / "blobs" / "sha256" / f"{content_hash}.csv"
    blob_path.parent.mkdir(parents=True)
    blob_path.write_bytes(content)
    manifest_path = raw_root / "manifests" / "cms_om_gv" / f"{run_id}.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(canonical_json_bytes(payload))
    return raw_root, manifest_path


def profiles_dir(tmp_path: Path) -> Path:
    """Create the exact credential-free dbt profile used by fixture builds."""
    destination = tmp_path / "profiles"
    destination.mkdir()
    (destination / "profiles.yml").write_bytes(PROFILE_EXAMPLE.read_bytes())
    return destination


def invoke_dbt(command: str | Sequence[str], profile_dir: Path) -> dbtRunnerResult:
    """Run dbt in-process with deterministic project/profile locations."""
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
    """Return stable failed-node names from a dbt execution result."""
    execution = result.result
    if execution is None or not hasattr(execution, "results"):
        return ()
    return tuple(
        item.node.name
        for item in execution.results
        if str(item.status).lower() not in {"success", "pass", "skipped"}
    )


def semantic_checksum(connection: duckdb.DuckDBPyConnection) -> str:
    """Hash the ordered semantic result rather than DuckDB physical bytes."""
    cursor = connection.execute(f"select * from {MODEL_RELATION} order by county_fips")
    columns = [item[0] for item in cursor.description]
    rows = [
        [str(value) if isinstance(value, Decimal) else value for value in row]
        for row in cursor.fetchall()
    ]
    payload = json.dumps(
        {"columns": columns, "rows": rows},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def test_dbt_project_parses_with_credential_free_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "parse.duckdb"
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    result = invoke_dbt("parse", profiles_dir(tmp_path))

    assert result.success, result.exception


def test_fixture_build_types_filters_and_rebuilds_deterministically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_root, manifest_path = materialize_snapshot(tmp_path)
    database_path = tmp_path / "fixture.duckdb"
    load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))
    profile_dir = profiles_dir(tmp_path)

    first_build = invoke_dbt("build", profile_dir)

    assert first_build.success, first_build.exception
    docs_result = invoke_dbt(("docs", "generate"), profile_dir)
    assert docs_result.success, docs_result.exception
    with duckdb.connect(str(database_path)) as connection:
        county_fips = tuple(
            row[0]
            for row in connection.execute(
                f"select county_fips from {MODEL_RELATION} order by county_fips"
            ).fetchall()
        )
        assert county_fips == (
            "01001",
            "01003",
            "01005",
            "01007",
            "01009",
            "11001",
        )
        first_checksum = semantic_checksum(connection)
        rows = {
            row[0]: row[1:]
            for row in connection.execute(
                f"""
                select county_fips,
                       {", ".join(f"{prefix}_raw, {prefix}, {prefix}_status" for prefix in METRIC_PREFIXES)}
                from {MODEL_RELATION}
                order by county_fips
                """
            ).fetchall()
        }

    for index, _prefix in enumerate(METRIC_PREFIXES):
        offset = index * 3
        assert rows["01003"][offset : offset + 3] == ("*", None, "suppressed")
        assert rows["01005"][offset : offset + 3] == (
            "",
            None,
            "unavailable_blank",
        )
        assert rows["01007"][offset : offset + 3] == (
            NA_RAW_VALUES[index],
            None,
            "unavailable_na",
        )
        assert rows["11001"][offset] == "0"
        assert rows["11001"][offset + 1] == 0
        assert rows["11001"][offset + 2] == "reported"
        assert rows["01009"][offset + 2] == "reported"
    assert rows["01009"][0] == " 42 "
    assert rows["01009"][1] == 42

    second_build = invoke_dbt("build", profile_dir)

    assert second_build.success, second_build.exception
    with duckdb.connect(str(database_path)) as connection:
        assert semantic_checksum(connection) == first_checksum


@pytest.mark.parametrize(
    ("case", "mutate", "expected_failure"),
    [
        (
            "invalid-numeric",
            lambda content: content.replace(
                b",0.0200,1500.0000,", b",BROKEN,1500.0000,", 1
            ),
            "assert_cms_numeric_values_valid",
        ),
        (
            "invalid-fips",
            lambda content: content.replace(
                b",01001,All,1000,", b",ABCDE,All,1000,", 1
            ),
            "assert_cms_county_fips_valid",
        ),
        (
            "duplicate-county-year",
            lambda content: (
                content
                + b"2024,County,AL-Synthetic Autauga Alias,01001,All,900,0.4,0.1,0.02,1400,190,0.14,490,duplicate county year\n"
            ),
            "assert_cms_county_year_unique",
        ),
    ],
)
def test_quality_failures_block_dbt_build_with_named_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    mutate,
    expected_failure: str,
) -> None:
    raw_root, manifest_path = materialize_snapshot(
        tmp_path,
        run_id=f"cms-om-gv-{case}",
        csv_bytes=mutate(FIXTURE_CSV.read_bytes()),
    )
    database_path = tmp_path / f"{case}.duckdb"
    load_cms_om_gv_snapshot(manifest_path, raw_root, database_path)
    monkeypatch.setenv("KIDNEY_CARE_DUCKDB_PATH", str(database_path))

    result = invoke_dbt("build", profiles_dir(tmp_path))

    assert not result.success
    assert expected_failure in result_failures(result)
