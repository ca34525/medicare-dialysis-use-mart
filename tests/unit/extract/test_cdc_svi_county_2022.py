"""Deterministic tests for paginated CDC/ATSDR SVI county extraction."""

from __future__ import annotations

import copy
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from kidney_care_mart.contracts.cdc_svi_county_2022 import REQUIRED_FIELDS
from kidney_care_mart.extract.cdc_svi_county_2022 import (
    SviManifestConflictError,
    SviPaginationError,
    SviProtocolError,
    extract_cdc_svi_county_2022,
    parse_count_response,
    parse_layer_metadata,
)
from kidney_care_mart.extract.http import RetryPolicy

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "cdc_svi_county_2022"
LAYER_PATH = FIXTURE_ROOT / "layer.json"
COUNT_PATH = FIXTURE_ROOT / "count.json"
PAGE_PATHS = (
    FIXTURE_ROOT / "pages" / "page-000000.json",
    FIXTURE_ROOT / "pages" / "page-000002.json",
)


class FakeResponse:
    """Context-managed exact-byte response used by extraction tests."""

    def __init__(self, content: bytes) -> None:
        self._stream = io.BytesIO(content)
        self.headers = {"Content-Length": str(len(content))}

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


class RoutingOpener:
    """Route metadata, count, and page requests to exact fixture bytes."""

    def __init__(self, pages: tuple[bytes, ...] | None = None) -> None:
        self.pages = pages or tuple(path.read_bytes() for path in PAGE_PATHS)
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/1"):
            return FakeResponse(LAYER_PATH.read_bytes())
        if query.get("returnCountOnly") == ["true"]:
            return FakeResponse(COUNT_PATH.read_bytes())
        offset = int(query["resultOffset"][0])
        return FakeResponse(self.pages[offset // 2])


def fixed_now() -> datetime:
    return datetime(2026, 8, 14, 20, 0, tzinfo=UTC)


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def extract_fixture(tmp_path: Path, *, pages: tuple[bytes, ...] | None = None):
    opener = RoutingOpener(pages)
    result = extract_cdc_svi_county_2022(
        run_id="cdc-svi-fixture-001",
        output_root=tmp_path / "raw",
        opener=opener,
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=fixed_now,
        page_size=2,
        retry_policy=RetryPolicy(max_attempts=2, base_delay_seconds=0),
    )
    return result, opener


def test_layer_metadata_contract_and_count_are_parsed() -> None:
    metadata = parse_layer_metadata(load_json(LAYER_PATH))

    assert metadata.layer_id == 1
    assert metadata.layer_name == "SVI2022 US county"
    assert metadata.object_id_field == "GRASP_ID"
    assert metadata.max_record_count == 2000
    assert metadata.supports_pagination
    assert metadata.supports_order_by
    assert metadata.additive_fields == ("ADDITIVE_FIELD",)
    assert len(metadata.fields) == 18
    assert parse_count_response(load_json(COUNT_PATH)) == 3


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update({"id": 2}),
        lambda payload: payload.update({"name": "SVI2022 US tract"}),
        lambda payload: payload.update({"objectIdField": "OBJECTID"}),
        lambda payload: payload.update({"maxRecordCount": 0}),
        lambda payload: payload["advancedQueryCapabilities"].update(
            {"supportsPagination": False}
        ),
        lambda payload: payload["advancedQueryCapabilities"].update(
            {"supportsOrderBy": False}
        ),
        lambda payload: payload["fields"].pop(0),
    ],
)
def test_incompatible_layer_metadata_is_blocking(mutation) -> None:
    payload = load_json(LAYER_PATH)
    mutation(payload)

    with pytest.raises(SviProtocolError):
        parse_layer_metadata(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"count": True},
        {"count": -1},
        {"count": "3144"},
        {"error": {"code": 500, "message": "upstream failure"}},
    ],
)
def test_invalid_count_response_is_blocking(payload: dict[str, object]) -> None:
    with pytest.raises(SviProtocolError):
        parse_count_response(payload)


def test_fixture_extraction_publishes_exact_pages_and_canonical_manifest(
    tmp_path: Path,
) -> None:
    result, opener = extract_fixture(tmp_path)

    assert result.status == "published"
    assert result.record_count == 3
    assert result.page_count == 2
    assert result.distinct_county_fips == 3
    assert result.distinct_object_ids == 3
    assert not result.content_noop
    assert not result.manifest_noop
    assert result.manifest_path.exists()
    assert len(result.page_paths) == 2
    assert result.page_paths[0].read_bytes() == PAGE_PATHS[0].read_bytes()
    assert result.page_paths[1].read_bytes() == PAGE_PATHS[1].read_bytes()

    payload = json.loads(result.manifest_path.read_bytes())
    assert payload["transport"]["page_offsets"] == [0, 2]
    assert payload["transport"]["record_count"] == 3
    assert payload["transport"]["return_geometry"] is False
    assert payload["transport"]["order_by"] == "GRASP_ID ASC"
    assert payload["schema"]["requested_fields"] == list(REQUIRED_FIELDS)
    assert payload["reconciliation"]["dc_11001_present"] is True
    assert payload["reconciliation"]["territory_row_count"] == 0

    parsed_calls = [(urlparse(call[0].full_url), call[0]) for call in opener.calls]
    page_calls = [item for item in parsed_calls if "resultOffset" in item[0].query]
    assert len(page_calls) == 2
    for parsed, request in page_calls:
        query = parse_qs(parsed.query)
        assert query["where"] == ["1=1"]
        assert query["outFields"] == [",".join(REQUIRED_FIELDS)]
        assert query["returnGeometry"] == ["false"]
        assert query["orderByFields"] == ["GRASP_ID ASC"]
        assert query["resultRecordCount"] == ["2"]
        assert request.headers["Accept"] == "application/json"


def mutate_page(index: int, mutation) -> tuple[bytes, ...]:
    payloads = [json.loads(path.read_bytes()) for path in PAGE_PATHS]
    mutation(payloads[index])
    return tuple(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
        for payload in payloads
    )


@pytest.mark.parametrize(
    ("pages", "message"),
    [
        (
            mutate_page(0, lambda payload: payload["features"].pop()),
            "expected 2 records",
        ),
        (
            mutate_page(
                1,
                lambda payload: payload["features"][0]["attributes"].update(
                    {"GRASP_ID": 2}
                ),
            ),
            "strictly increasing",
        ),
        (
            mutate_page(
                1,
                lambda payload: payload["features"][0]["attributes"].update(
                    {"ST": "01", "STCNTY": "01001"}
                ),
            ),
            "Duplicate county FIPS",
        ),
        (
            mutate_page(
                0,
                lambda payload: payload["features"][0]["attributes"].pop("ST"),
            ),
            "missing required attributes",
        ),
        (
            mutate_page(
                0,
                lambda payload: payload["features"][0].update(
                    {"geometry": {"x": 1, "y": 2}}
                ),
            ),
            "geometry",
        ),
    ],
)
def test_page_or_global_reconciliation_failure_cannot_publish(
    tmp_path: Path,
    pages: tuple[bytes, ...],
    message: str,
) -> None:
    with pytest.raises(SviPaginationError, match=message):
        extract_fixture(tmp_path, pages=pages)

    assert not (tmp_path / "raw" / "manifests").exists()
    assert not list((tmp_path / "raw" / "blobs").glob("**/*"))


def test_arcgis_error_page_is_not_treated_as_a_transient_transport_failure(
    tmp_path: Path,
) -> None:
    pages = (
        b'{"error":{"code":400,"message":"bad query"}}',
        PAGE_PATHS[1].read_bytes(),
    )

    with pytest.raises(SviProtocolError, match="bad query"):
        extract_fixture(tmp_path, pages=pages)


def test_same_snapshot_new_run_reuses_verified_page_blobs(tmp_path: Path) -> None:
    first, _ = extract_fixture(tmp_path)
    second = extract_cdc_svi_county_2022(
        run_id="cdc-svi-fixture-002",
        output_root=tmp_path / "raw",
        opener=RoutingOpener(),
        sleep=lambda _seconds: None,
        jitter=lambda: 0.0,
        now=fixed_now,
        page_size=2,
        retry_policy=RetryPolicy(max_attempts=1),
    )

    assert not first.content_noop
    assert second.content_noop
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert first.page_paths == second.page_paths
    assert first.manifest_path != second.manifest_path


def test_same_run_is_idempotent_and_conflicting_lineage_is_blocked(
    tmp_path: Path,
) -> None:
    first, _ = extract_fixture(tmp_path)
    second, _ = extract_fixture(tmp_path)

    assert second.manifest_noop
    assert second.manifest_path == first.manifest_path

    changed_pages = mutate_page(
        1,
        lambda payload: payload["features"][0]["attributes"].update({"EP_POV150": 7.9}),
    )
    with pytest.raises(SviManifestConflictError, match="already exists"):
        extract_fixture(tmp_path, pages=changed_pages)


def test_corrupt_existing_page_blob_blocks_content_reuse(tmp_path: Path) -> None:
    first, _ = extract_fixture(tmp_path)
    first.page_paths[0].write_bytes(b"corrupt")

    with pytest.raises(SviManifestConflictError, match="integrity"):
        extract_cdc_svi_county_2022(
            run_id="cdc-svi-fixture-002",
            output_root=tmp_path / "raw",
            opener=RoutingOpener(),
            sleep=lambda _seconds: None,
            jitter=lambda: 0.0,
            now=fixed_now,
            page_size=2,
            retry_policy=RetryPolicy(max_attempts=1),
        )


def test_invalid_run_id_fails_before_network_or_filesystem_work(tmp_path: Path) -> None:
    opener = RoutingOpener()

    with pytest.raises(ValueError, match="run ID"):
        extract_cdc_svi_county_2022(
            run_id="../escape",
            output_root=tmp_path / "raw",
            opener=opener,
        )

    assert opener.calls == []
    assert not (tmp_path / "raw").exists()


def test_duplicate_required_metadata_field_is_not_hidden_by_mapping() -> None:
    payload = load_json(LAYER_PATH)
    duplicate = copy.deepcopy(payload["fields"][0])
    payload["fields"].append(duplicate)

    with pytest.raises(SviProtocolError, match="appears more than once"):
        parse_layer_metadata(payload)
