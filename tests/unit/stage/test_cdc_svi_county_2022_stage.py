"""Tests for manifest-driven SVI raw loading into DuckDB."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import duckdb
import pytest

from kidney_care_mart.contracts.cdc_svi_county_2022 import REQUIRED_FIELDS
from kidney_care_mart.extract.cdc_svi_county_2022 import (
    extract_cdc_svi_county_2022,
)
from kidney_care_mart.extract.http import RetryPolicy
from kidney_care_mart.extract.manifest import canonical_json_bytes
from kidney_care_mart.stage.cdc_svi_county_2022 import (
    SviStageLoadConflictError,
    SviStageLoadError,
    load_cdc_svi_county_2022_snapshot,
)

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "cdc_svi_county_2022"


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
    def __call__(self, request: Request, _timeout: float) -> FakeResponse:
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/1"):
            path = FIXTURE_ROOT / "layer.json"
        elif query.get("returnCountOnly") == ["true"]:
            path = FIXTURE_ROOT / "count.json"
        else:
            offset = int(query["resultOffset"][0])
            path = FIXTURE_ROOT / "pages" / f"page-{offset:06d}.json"
        return FakeResponse(path.read_bytes())


def fixed_now() -> datetime:
    return datetime(2026, 8, 14, 20, 0, tzinfo=UTC)


def materialize_fixture_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    raw_root = tmp_path / "raw"
    result = extract_cdc_svi_county_2022(
        run_id="cdc-svi-staging-fixture-001",
        output_root=raw_root,
        opener=FixtureOpener(),
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=fixed_now,
        page_size=2,
        retry_policy=RetryPolicy(max_attempts=1),
    )
    return raw_root, result.manifest_path


def test_verified_snapshot_loads_raw_tokens_and_null_without_float_round_trip(
    tmp_path: Path,
) -> None:
    raw_root, manifest_path = materialize_fixture_snapshot(tmp_path)
    database_path = tmp_path / "svi.duckdb"

    result = load_cdc_svi_county_2022_snapshot(
        manifest_path=manifest_path,
        raw_root=raw_root,
        database_path=database_path,
    )

    assert result.status == "loaded"
    assert result.row_count == 3
    assert result.page_count == 2
    assert not result.database_noop
    with duckdb.connect(str(database_path), read_only=True) as connection:
        columns = connection.execute(
            "describe select * from raw.cdc_svi_county_2022"
        ).fetchall()
        types = {name: data_type for name, data_type, *_ in columns}
        assert all(types[name] == "VARCHAR" for name in REQUIRED_FIELDS)
        values = connection.execute(
            """
            select
                "STCNTY",
                "RPL_THEMES",
                "RPL_THEME1",
                "EP_AGE65",
                "GRASP_ID"
            from raw.cdc_svi_county_2022
            order by cast("GRASP_ID" as integer)
            """
        ).fetchall()
    assert values == [
        ("01001", "0", "0.75", "20.1", "1"),
        ("11001", "0.75", "-999", "14.3", "2"),
        ("02013", "1", "0.5", None, "3"),
    ]


def test_loaded_rows_retain_page_and_snapshot_lineage(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_snapshot(tmp_path)
    database_path = tmp_path / "svi.duckdb"

    result = load_cdc_svi_county_2022_snapshot(
        manifest_path,
        raw_root,
        database_path,
    )

    with duckdb.connect(str(database_path), read_only=True) as connection:
        lineage = connection.execute(
            """
            select
                source_id,
                source_manifest_run_id,
                source_snapshot_sha256,
                source_page_index,
                source_page_offset,
                count(*)
            from raw.cdc_svi_county_2022
            group by all
            order by source_page_index
            """
        ).fetchall()
        audit = connection.execute(
            """
            select page_count, row_count, snapshot_sha256
            from raw.cdc_svi_county_2022_load_audit
            """
        ).fetchone()
    assert lineage == [
        (
            "cdc_svi_county_2022",
            "cdc-svi-staging-fixture-001",
            result.snapshot_sha256,
            0,
            0,
            2,
        ),
        (
            "cdc_svi_county_2022",
            "cdc-svi-staging-fixture-001",
            result.snapshot_sha256,
            1,
            2,
            1,
        ),
    ]
    assert audit == (2, 3, result.snapshot_sha256)


def test_identical_load_is_a_database_noop(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_snapshot(tmp_path)
    database_path = tmp_path / "svi.duckdb"

    first = load_cdc_svi_county_2022_snapshot(
        manifest_path,
        raw_root,
        database_path,
    )
    second = load_cdc_svi_county_2022_snapshot(
        manifest_path,
        raw_root,
        database_path,
    )

    assert not first.database_noop
    assert second.database_noop
    assert second.status == "database_noop"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload.update({"manifest_format_version": 2}), "format"),
        (
            lambda payload: payload["source"].update(
                {"logical_source_id": "other_source"}
            ),
            "source",
        ),
        (
            lambda payload: payload["schema"].update(
                {"contract_version": "cdc_svi_county_2022.raw.v0"}
            ),
            "contract",
        ),
        (
            lambda payload: payload["content"].update({"snapshot_sha256": "0" * 64}),
            "snapshot",
        ),
        (
            lambda payload: payload["transport"].update({"return_geometry": True}),
            "shape",
        ),
    ],
)
def test_unsupported_or_unreconciled_manifest_cannot_create_database(
    tmp_path: Path,
    mutation,
    message: str,
) -> None:
    raw_root, manifest_path = materialize_fixture_snapshot(tmp_path)
    payload = json.loads(manifest_path.read_bytes())
    mutation(payload)
    manifest_path.write_bytes(canonical_json_bytes(payload))
    database_path = tmp_path / "svi.duckdb"

    with pytest.raises(SviStageLoadError, match=message):
        load_cdc_svi_county_2022_snapshot(
            manifest_path,
            raw_root,
            database_path,
        )

    assert not database_path.exists()


def test_manifest_page_path_cannot_escape_raw_root(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_snapshot(tmp_path)
    payload = json.loads(manifest_path.read_bytes())
    payload["pages"][0]["blob_path"] = "../outside.json"
    manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(SviStageLoadError, match="escape"):
        load_cdc_svi_county_2022_snapshot(
            manifest_path,
            raw_root,
            tmp_path / "svi.duckdb",
        )


def test_corrupt_page_cannot_create_database(tmp_path: Path) -> None:
    raw_root, manifest_path = materialize_fixture_snapshot(tmp_path)
    payload = json.loads(manifest_path.read_bytes())
    page_path = raw_root.joinpath(*payload["pages"][0]["blob_path"].split("/"))
    page_path.write_bytes(b"corrupt")
    database_path = tmp_path / "svi.duckdb"

    with pytest.raises(SviStageLoadError, match="integrity"):
        load_cdc_svi_county_2022_snapshot(
            manifest_path,
            raw_root,
            database_path,
        )

    assert not database_path.exists()


def test_conflicting_manifest_cannot_overwrite_existing_database(
    tmp_path: Path,
) -> None:
    raw_root, manifest_path = materialize_fixture_snapshot(tmp_path)
    database_path = tmp_path / "svi.duckdb"
    load_cdc_svi_county_2022_snapshot(manifest_path, raw_root, database_path)
    payload = json.loads(manifest_path.read_bytes())
    payload["pipeline"]["run_id"] = "different-run"
    manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(SviStageLoadConflictError, match="different manifest"):
        load_cdc_svi_county_2022_snapshot(
            manifest_path,
            raw_root,
            database_path,
        )

    with duckdb.connect(str(database_path), read_only=True) as connection:
        assert connection.execute(
            "select count(*) from raw.cdc_svi_county_2022"
        ).fetchone() == (3,)
