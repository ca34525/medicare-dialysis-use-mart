"""Network-free raw-string loading tests for the facility snapshot."""

from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from kidney_care_mart.contracts.cms_dialysis_facility import REQUIRED_FIELDS
from kidney_care_mart.extract.cms_dialysis_facility import (
    CATALOG_URL,
    DATASTORE_SCHEMA_URL,
    extract_cms_dialysis_facility,
)
from kidney_care_mart.extract.http import RetryPolicy
from kidney_care_mart.stage.cms_dialysis_facility import (
    FacilityStageLoadError,
    load_cms_dialysis_facility_snapshot,
)

FIXTURE_DIR = Path(__file__).parents[2] / "fixtures" / "cms_dialysis_facility"
CSV_PATH = FIXTURE_DIR / "staging.csv"


class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self._stream = io.BytesIO(content)
        self.headers = {
            "Content-Length": str(len(content)),
            "Content-Type": "text/csv; charset=utf-8",
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


def _materialize_snapshot(tmp_path: Path) -> tuple[Path, Path]:
    catalog = json.loads((FIXTURE_DIR / "catalog.json").read_bytes())

    def json_loader(url: str) -> dict[str, object]:
        if url == CATALOG_URL:
            return catalog
        if url == DATASTORE_SCHEMA_URL:
            return _api_payload()
        raise AssertionError(f"unexpected fixture URL: {url}")

    result = extract_cms_dialysis_facility(
        run_id="facility-stage-fixture-001",
        output_root=tmp_path / "raw",
        json_loader=json_loader,
        opener=lambda _request, _timeout: FakeResponse(CSV_PATH.read_bytes()),
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=lambda: datetime(2026, 8, 15, 12, 0, tzinfo=UTC),
        retry_policy=RetryPolicy(max_attempts=1),
    )
    return result.manifest_path, tmp_path / "raw"


def test_verified_facility_manifest_loads_raw_strings_atomically(
    tmp_path: Path,
) -> None:
    manifest_path, raw_root = _materialize_snapshot(tmp_path)
    database_path = tmp_path / "facility.duckdb"

    first = load_cms_dialysis_facility_snapshot(
        manifest_path,
        raw_root,
        database_path,
    )
    second = load_cms_dialysis_facility_snapshot(
        manifest_path,
        raw_root,
        database_path,
    )

    assert first.status == "loaded"
    assert first.row_count == 3
    assert not first.database_noop
    assert second.status == "database_noop"
    assert second.database_noop
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            """
            select "CMS Certification Number (CCN)",
                   "# of Dialysis Stations",
                   "Five Star",
                   source_snapshot_sha256
            from raw.cms_dialysis_facility
            order by "CMS Certification Number (CCN)"
            """
        ).fetchall()
        audit = connection.execute(
            "select row_count, distinct_ccn_count, page_count "
            "from raw.cms_dialysis_facility_load_audit"
        ).fetchone()
    assert rows[0][:3] == ("012345", "12", "4")
    assert rows[1][:3] == ("123456", "0", "")
    assert len(rows[0][3]) == 64
    assert audit == (3, 3, 1)


def test_corrupt_facility_blob_cannot_publish_a_database(tmp_path: Path) -> None:
    manifest_path, raw_root = _materialize_snapshot(tmp_path)
    payload = json.loads(manifest_path.read_bytes())
    blob = raw_root.joinpath(*payload["storage"]["blob_path"].split("/"))
    blob.write_bytes(b"corrupt")
    database_path = tmp_path / "facility.duckdb"

    with pytest.raises(FacilityStageLoadError, match="integrity validation"):
        load_cms_dialysis_facility_snapshot(
            manifest_path,
            raw_root,
            database_path,
        )

    assert not database_path.exists()
