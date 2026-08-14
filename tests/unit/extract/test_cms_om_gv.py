"""CMS-specific resolver and fixture extraction tests with no network access."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request

import pytest

from kidney_care_mart.contracts.cms_om_gv import REQUIRED_COLUMNS
from kidney_care_mart.extract.cms_om_gv import (
    CATALOG_URL,
    DATA_VIEWER_URL,
    EXPECTED_LANDING_URL,
    STABLE_DATASET_ID,
    CatalogResolutionError,
    CmsMetadataError,
    extract_cms_om_gv,
    parse_data_viewer_metadata,
    resolve_current_source,
)
from kidney_care_mart.extract.http import RetryPolicy

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "cms_om_gv"
CATALOG_FIXTURE_PATH = FIXTURE_ROOT / "catalog.json"
DOWNLOAD_FIXTURE_PATH = FIXTURE_ROOT / "download.csv"


class FakeResponse:
    """Context-managed response used by the source orchestration tests."""

    def __init__(self, content: bytes, headers: dict[str, str]) -> None:
        self._stream = io.BytesIO(content)
        self.headers = headers

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self._stream.read(size)


class SequenceOpener:
    """Return configured responses and retain calls for assertions."""

    def __init__(self, outcomes: list[FakeResponse | BaseException]) -> None:
        self.outcomes = outcomes
        self.calls: list[tuple[Request, float]] = []

    def __call__(self, request: Request, timeout: float) -> FakeResponse:
        self.calls.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def catalog_fixture() -> dict[str, object]:
    """Load a fresh official-shaped catalog fixture."""
    return json.loads(CATALOG_FIXTURE_PATH.read_text(encoding="utf-8"))


def download_header() -> list[str]:
    """Read the raw fixture header."""
    with DOWNLOAD_FIXTURE_PATH.open(encoding="utf-8", newline="") as fixture:
        return next(csv.reader(fixture))


def metadata_fixture() -> dict[str, object]:
    """Build current data-viewer metadata that reconciles to the fixture."""
    content = DOWNLOAD_FIXTURE_PATH.read_bytes()
    header = download_header()
    return {
        "meta": {
            "success": True,
            "headers": header,
            "data_file_name": "cms-om-gv.csv",
            "data_file_url": "/sites/default/files/current/cms-om-gv.csv",
            "data_file_meta_data": {
                "csvFileSize": len(content),
                "csvColumnTypes": {
                    name: REQUIRED_COLUMNS.get(name, "TEXT") for name in header
                },
                "csvFileSHA1": hashlib.sha1(content).hexdigest(),
            },
            "total_rows": 2,
            "offset": 0,
            "size": 1,
            "tableSchema": {"hash": "fixture-cms-table-schema-hash"},
        },
        "data": [],
    }


def response_for_fixture() -> FakeResponse:
    """Return one complete source-shaped CSV response."""
    content = DOWNLOAD_FIXTURE_PATH.read_bytes()
    return FakeResponse(
        content,
        {
            "Content-Length": str(len(content)),
            "ETag": '"fixture-etag"',
            "Last-Modified": "Fri, 14 Aug 2026 12:00:00 GMT",
        },
    )


def fixture_loader(payload: dict[str, object]):
    """Create a URL loader for catalog and metadata fixture payloads."""
    metadata = metadata_fixture()

    def load(url: str) -> dict[str, object]:
        if url == CATALOG_URL:
            return payload
        if url == DATA_VIEWER_URL:
            return metadata
        raise AssertionError(f"unexpected fixture URL: {url}")

    return load


def test_catalog_resolver_selects_stable_dataset_and_current_full_csv() -> None:
    resolved = resolve_current_source(catalog_fixture())

    assert resolved.stable_dataset_id == STABLE_DATASET_ID
    assert resolved.catalog_url == CATALOG_URL
    assert resolved.landing_url == EXPECTED_LANDING_URL
    assert resolved.download_url == (
        "https://data.cms.gov/sites/default/files/current/cms-om-gv.csv"
    )
    assert resolved.modified_date == "2026-05-15"
    assert resolved.source_release == "2014-01-01/2024-12-31"
    assert resolved.data_viewer_url == DATA_VIEWER_URL


def test_catalog_resolver_ignores_api_distribution() -> None:
    catalog = catalog_fixture()
    intended = catalog["dataset"][0]
    intended["distribution"].reverse()

    resolved = resolve_current_source(catalog)

    assert resolved.download_url.endswith("cms-om-gv.csv")


def test_zero_stable_dataset_matches_is_blocking() -> None:
    catalog = catalog_fixture()
    catalog["dataset"] = catalog["dataset"][1:]

    with pytest.raises(CatalogResolutionError, match=r"exactly one.*found 0"):
        resolve_current_source(catalog)


def test_multiple_stable_dataset_matches_is_blocking() -> None:
    catalog = catalog_fixture()
    catalog["dataset"].append(copy.deepcopy(catalog["dataset"][0]))

    with pytest.raises(CatalogResolutionError, match=r"exactly one.*found 2"):
        resolve_current_source(catalog)


def test_stable_identity_must_be_corroborated_by_official_title_and_landing() -> None:
    catalog = catalog_fixture()
    catalog["dataset"][0]["title"] = "Unexpected dataset"

    with pytest.raises(CatalogResolutionError, match="title"):
        resolve_current_source(catalog)


def test_missing_current_full_csv_is_blocking() -> None:
    catalog = catalog_fixture()
    catalog["dataset"][0]["distribution"] = [catalog["dataset"][0]["distribution"][0]]

    with pytest.raises(CatalogResolutionError, match="full CSV"):
        resolve_current_source(catalog)


def test_nonofficial_csv_url_is_rejected() -> None:
    catalog = catalog_fixture()
    catalog["dataset"][0]["distribution"][1]["downloadURL"] = (
        "https://example.test/arbitrary.csv"
    )

    with pytest.raises(CatalogResolutionError, match="official CMS HTTPS"):
        resolve_current_source(catalog)


def test_data_viewer_metadata_retains_order_and_declared_types() -> None:
    resolved = resolve_current_source(catalog_fixture())

    metadata = parse_data_viewer_metadata(metadata_fixture(), resolved)

    assert tuple(column.name for column in metadata.columns) == tuple(download_header())
    assert metadata.columns[0].declared_type == "NUMERIC"
    assert metadata.columns[-1].declared_type == "TEXT"
    assert metadata.expected_row_count == 2
    assert metadata.expected_byte_count == len(DOWNLOAD_FIXTURE_PATH.read_bytes())
    assert metadata.cms_table_schema_hash == "fixture-cms-table-schema-hash"


def test_metadata_must_reconcile_to_catalog_download_url() -> None:
    payload = metadata_fixture()
    payload["meta"]["data_file_url"] = "/sites/default/files/other.csv"

    with pytest.raises(CmsMetadataError, match="download URL"):
        parse_data_viewer_metadata(
            payload,
            resolve_current_source(catalog_fixture()),
        )


def test_metadata_missing_column_type_is_blocking() -> None:
    payload = metadata_fixture()
    del payload["meta"]["data_file_meta_data"]["csvColumnTypes"]["YEAR"]

    with pytest.raises(CmsMetadataError, match="column types"):
        parse_data_viewer_metadata(
            payload,
            resolve_current_source(catalog_fixture()),
        )


def test_fixture_extraction_publishes_blob_and_canonical_manifest(
    tmp_path: Path,
) -> None:
    catalog = catalog_fixture()
    opener = SequenceOpener(
        [URLError("fixture transient failure"), response_for_fixture()]
    )
    sleeps: list[float] = []

    result = extract_cms_om_gv(
        run_id="cms-om-gv-fixture-001",
        output_root=tmp_path / "raw",
        json_loader=fixture_loader(catalog),
        opener=opener,
        sleep=sleeps.append,
        jitter=lambda: 0.0,
        now=lambda: datetime(2026, 8, 14, 12, 0, tzinfo=UTC),
        retry_policy=RetryPolicy(
            max_attempts=2,
            base_delay_seconds=1.0,
            max_delay_seconds=2.0,
        ),
    )

    assert result.status == "published"
    assert result.blob_path.read_bytes() == DOWNLOAD_FIXTURE_PATH.read_bytes()
    assert result.manifest_path.exists()
    assert result.row_count == 2
    assert result.retry_count == 1
    assert result.additive_columns == ("ADDITIVE_NOTE",)
    assert not result.content_noop
    assert not result.manifest_noop
    assert sleeps == [1.0]
    manifest = json.loads(result.manifest_path.read_bytes())
    assert manifest["transport"] == {
        "mode": "full_csv",
        "page_count": 1,
        "record_count": 2,
    }
    assert manifest["content"]["sha256"] == result.content_sha256
    assert manifest["content"]["byte_count"] == len(DOWNLOAD_FIXTURE_PATH.read_bytes())
    assert manifest["schema"]["additive_columns"] == ["ADDITIVE_NOTE"]
    assert (
        manifest["storage"]["blob_path"]
        == result.blob_path.relative_to(tmp_path / "raw").as_posix()
    )
    assert len(opener.calls) == 2


def test_same_content_new_run_reuses_blob(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    loader = fixture_loader(catalog_fixture())

    def fixed_now() -> datetime:
        return datetime(2026, 8, 14, 12, 0, tzinfo=UTC)

    first = extract_cms_om_gv(
        run_id="cms-om-gv-fixture-001",
        output_root=output_root,
        json_loader=loader,
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )

    second = extract_cms_om_gv(
        run_id="cms-om-gv-fixture-002",
        output_root=output_root,
        json_loader=loader,
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )

    assert second.status == "content_noop"
    assert second.content_noop
    assert second.blob_path == first.blob_path
    assert len(list((output_root / "blobs" / "sha256").glob("*.csv"))) == 1


def test_contract_failure_happens_before_download_or_publication(
    tmp_path: Path,
) -> None:
    metadata = metadata_fixture()
    types = metadata["meta"]["data_file_meta_data"]["csvColumnTypes"]
    types["BENES_OP_DLYS_PCT"] = "TEXT"

    def loader(url: str) -> dict[str, object]:
        if url == CATALOG_URL:
            return catalog_fixture()
        if url == DATA_VIEWER_URL:
            return metadata
        raise AssertionError(url)

    opener = SequenceOpener([response_for_fixture()])

    with pytest.raises(CmsMetadataError, match="BENES_OP_DLYS_PCT"):
        extract_cms_om_gv(
            run_id="cms-om-gv-fixture-bad-schema",
            output_root=tmp_path / "raw",
            json_loader=loader,
            opener=opener,
        )

    assert not opener.calls
    assert not (tmp_path / "raw" / "blobs").exists()
    assert not (tmp_path / "raw" / "manifests").exists()


def test_truncated_download_cannot_publish(tmp_path: Path) -> None:
    complete = DOWNLOAD_FIXTURE_PATH.read_bytes()
    truncated = complete[:100]
    opener = SequenceOpener(
        [FakeResponse(truncated, {"Content-Length": str(len(complete))})]
    )

    with pytest.raises(Exception, match="Content-Length"):
        extract_cms_om_gv(
            run_id="cms-om-gv-fixture-truncated",
            output_root=tmp_path / "raw",
            json_loader=fixture_loader(catalog_fixture()),
            opener=opener,
            retry_policy=RetryPolicy(max_attempts=1),
        )

    assert not (tmp_path / "raw" / "blobs").exists()
    assert not (tmp_path / "raw" / "manifests").exists()


def test_invalid_run_id_fails_before_any_live_seam(tmp_path: Path) -> None:
    def loader(_url: str) -> dict[str, object]:
        raise AssertionError("invalid run ID must fail before metadata resolution")

    with pytest.raises(ValueError, match="run ID"):
        extract_cms_om_gv(
            run_id="../escape",
            output_root=tmp_path / "raw",
            json_loader=loader,
        )
