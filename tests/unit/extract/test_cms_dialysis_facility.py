"""Network-free resolver, transport, and manifest tests for Plan 008."""

from __future__ import annotations

import copy
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request

import pytest

from kidney_care_mart.contracts.cms_dialysis_facility import REQUIRED_FIELDS, ApiField
from kidney_care_mart.extract.cms_dialysis_facility import (
    CATALOG_URL,
    DATASTORE_SCHEMA_URL,
    DICTIONARY_SHA256,
    EXPECTED_LANDING_URL,
    METADATA_URL,
    STABLE_DATASET_ID,
    CatalogResolutionError,
    FacilityCsvError,
    FacilityManifestConflictError,
    FacilityMetadataError,
    extract_cms_dialysis_facility,
    load_and_reconcile_facility_snapshot,
    parse_api_metadata,
    resolve_current_source,
    validate_facility_csv,
    verify_schema_evidence,
)
from kidney_care_mart.extract.http import RetryPolicy
from kidney_care_mart.extract.manifest import canonical_json_bytes

FIXTURE_ROOT = Path(__file__).parents[2] / "fixtures" / "cms_dialysis_facility"
CATALOG_PATH = FIXTURE_ROOT / "catalog.json"
DOWNLOAD_PATH = FIXTURE_ROOT / "download.csv"


class FakeResponse:
    """Small context-managed response for injected HTTP tests."""

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
    """Return configured outcomes and retain every request."""

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
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def download_header() -> list[str]:
    with DOWNLOAD_PATH.open(encoding="utf-8", newline="") as fixture:
        return next(csv.reader(fixture))


def api_payload() -> dict[str, object]:
    required_by_header = {field.csv_header: field for field in REQUIRED_FIELDS}
    fields: dict[str, dict[str, str]] = {}
    for header in download_header():
        mapping = required_by_header.get(header)
        api_name = (
            mapping.api_field_name if mapping is not None else "synthetic_additive_note"
        )
        fields[api_name] = {
            "type": "text",
            "mysql_type": "text",
            "description": header,
        }
    return {
        "results": [],
        "count": 3,
        "schema": {"fixture-resource-id": {"fields": fields}},
        "query": {"limit": 1, "offset": 0},
    }


def fixture_loader(
    catalog: dict[str, object] | None = None,
    api: dict[str, object] | None = None,
):
    catalog_value = catalog or catalog_fixture()
    api_value = api or api_payload()

    def load(url: str) -> dict[str, object]:
        if url == CATALOG_URL:
            return catalog_value
        if url == DATASTORE_SCHEMA_URL:
            return api_value
        raise AssertionError(f"unexpected fixture URL: {url}")

    return load


def response_for_fixture(
    *,
    content: bytes | None = None,
    content_type: str = "text/csv; charset=utf-8",
) -> FakeResponse:
    body = DOWNLOAD_PATH.read_bytes() if content is None else content
    return FakeResponse(
        body,
        {
            "Content-Length": str(len(body)),
            "Content-Type": content_type,
            "ETag": '"fixture-etag"',
            "Last-Modified": "Sat, 15 Aug 2026 12:00:00 GMT",
        },
    )


def fixed_now() -> datetime:
    return datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


def test_resolver_selects_exact_stable_listing_and_complete_csv() -> None:
    resolved = resolve_current_source(catalog_fixture())

    assert resolved.stable_dataset_id == STABLE_DATASET_ID
    assert resolved.catalog_url == CATALOG_URL
    assert resolved.metadata_url == METADATA_URL
    assert resolved.landing_url == EXPECTED_LANDING_URL
    assert resolved.dictionary_url.endswith("DF_Data_Dictionary.pdf")
    assert resolved.download_url.endswith("DFC_FACILITY.csv")
    assert resolved.source_release == "2026-07-15"
    assert resolved.modified_date == "2026-06-16"
    assert resolved.next_update_date == "2026-10-28"


def test_zero_and_multiple_stable_matches_are_blocking() -> None:
    catalog = catalog_fixture()
    catalog["dataset"] = catalog["dataset"][1:]
    with pytest.raises(CatalogResolutionError, match=r"exactly one.*found 0"):
        resolve_current_source(catalog)

    duplicate = catalog_fixture()
    duplicate["dataset"].append(copy.deepcopy(duplicate["dataset"][0]))
    with pytest.raises(CatalogResolutionError, match=r"exactly one.*found 2"):
        resolve_current_source(duplicate)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("title", "Dialysis Facility - State Averages", "title"),
        (
            "landingPage",
            "https://data.cms.gov/provider-data/dataset/other",
            "landing",
        ),
    ),
)
def test_stable_identity_requires_exact_corroboration(
    field: str,
    value: str,
    message: str,
) -> None:
    catalog = catalog_fixture()
    catalog["dataset"][0][field] = value

    with pytest.raises(CatalogResolutionError, match=message):
        resolve_current_source(catalog)


@pytest.mark.parametrize(
    "download_url",
    (
        "https://example.test/arbitrary.csv",
        "https://data.cms.gov/provider-data/sample.csv",
        "https://data.cms.gov/provider-data/state-averages.csv",
        "https://data.cms.gov/provider-data/national-averages.csv",
        "https://data.cms.gov/provider-data/archive.zip",
    ),
)
def test_nonofficial_partial_or_non_csv_distributions_are_rejected(
    download_url: str,
) -> None:
    catalog = catalog_fixture()
    catalog["dataset"][0]["distribution"][0]["downloadURL"] = download_url

    with pytest.raises(CatalogResolutionError, match="full CSV"):
        resolve_current_source(catalog)


def test_non_csv_catalog_distribution_is_rejected() -> None:
    catalog = catalog_fixture()
    catalog["dataset"][0]["distribution"][0]["mediaType"] = "text/html"

    with pytest.raises(CatalogResolutionError, match="full CSV"):
        resolve_current_source(catalog)


def test_api_metadata_preserves_order_and_validates_contract() -> None:
    metadata = parse_api_metadata(api_payload())

    assert metadata.expected_row_count == 3
    assert tuple(field.csv_header for field in metadata.fields) == tuple(
        download_header()
    )
    assert metadata.additive_fields == ("Synthetic Additive Note",)
    assert metadata.fields[0] == ApiField(
        api_field_name="cms_certification_number_ccn",
        csv_header="CMS Certification Number (CCN)",
        declared_type="text",
    )


def test_committed_schema_evidence_is_reparsed_before_ingestion(
    tmp_path: Path,
) -> None:
    schema_path = (
        Path(__file__).parents[3]
        / "docs"
        / "source-schemas"
        / "cms_dialysis_facility.schema.json"
    )
    verify_schema_evidence(schema_path)

    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    payload["required_semantic_mapping"][0]["dictionary_label"] = "Drifted label"
    drifted_path = tmp_path / "drifted.schema.json"
    drifted_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(FacilityMetadataError, match="schema evidence"):
        verify_schema_evidence(drifted_path)


def test_api_schema_failure_occurs_before_full_download(tmp_path: Path) -> None:
    api = api_payload()
    fields = api["schema"]["fixture-resource-id"]["fields"]
    fields.pop("patient_survival_data_availability_code")
    opener = SequenceOpener([response_for_fixture()])

    with pytest.raises(FacilityMetadataError, match="survival"):
        extract_cms_dialysis_facility(
            run_id="facility-bad-schema",
            output_root=tmp_path / "raw",
            json_loader=fixture_loader(api=api),
            opener=opener,
        )

    assert opener.calls == []
    assert not (tmp_path / "raw" / "blobs").exists()


def test_csv_validation_counts_quoted_newline_and_preserves_raw_rows(
    tmp_path: Path,
) -> None:
    with DOWNLOAD_PATH.open(encoding="utf-8", newline="") as fixture:
        rows = list(csv.reader(fixture))
    rows[1][2] = "Synthetic, label\ncontinued"
    path = tmp_path / "quoted.csv"
    with path.open("w", encoding="utf-8", newline="") as output:
        csv.writer(output, lineterminator="\n").writerows(rows)

    evidence = validate_facility_csv(
        path,
        parse_api_metadata(api_payload()).fields,
        expected_row_count=3,
    )

    assert evidence.row_count == 3
    assert evidence.distinct_ccn_count == 3
    assert evidence.leading_zero_ccn_count == 1


def test_duplicate_or_blank_ccn_blocks_complete_csv(tmp_path: Path) -> None:
    with DOWNLOAD_PATH.open(encoding="utf-8", newline="") as fixture:
        rows = list(csv.reader(fixture))
    rows[3][0] = rows[1][0]
    duplicate = tmp_path / "duplicate.csv"
    with duplicate.open("w", encoding="utf-8", newline="") as output:
        csv.writer(output, lineterminator="\n").writerows(rows)

    with pytest.raises(FacilityCsvError, match=r"duplicate.*row 4.*row 2"):
        validate_facility_csv(
            duplicate,
            parse_api_metadata(api_payload()).fields,
        )

    rows[3][0] = ""
    blank = tmp_path / "blank.csv"
    with blank.open("w", encoding="utf-8", newline="") as output:
        csv.writer(output, lineterminator="\n").writerows(rows)

    with pytest.raises(FacilityCsvError, match=r"CCN is blank.*row 4"):
        validate_facility_csv(
            blank,
            parse_api_metadata(api_payload()).fields,
        )


def test_actual_ordered_header_must_match_api_metadata(tmp_path: Path) -> None:
    with DOWNLOAD_PATH.open(encoding="utf-8", newline="") as fixture:
        rows = list(csv.reader(fixture))
    rows[0][0] = "Friendly but unverified CCN"
    changed = tmp_path / "changed-header.csv"
    with changed.open("w", encoding="utf-8", newline="") as output:
        csv.writer(output, lineterminator="\n").writerows(rows)

    with pytest.raises(FacilityCsvError, match="ordered Provider Data metadata"):
        validate_facility_csv(
            changed,
            parse_api_metadata(api_payload()).fields,
        )


def test_extraction_publishes_unchanged_blob_and_canonical_manifest(
    tmp_path: Path,
) -> None:
    opener = SequenceOpener([response_for_fixture()])

    result = extract_cms_dialysis_facility(
        run_id="facility-fixture-001",
        output_root=tmp_path / "raw",
        json_loader=fixture_loader(),
        opener=opener,
        now=fixed_now,
    )

    assert result.status == "published"
    assert result.blob_path.read_bytes() == DOWNLOAD_PATH.read_bytes()
    assert result.row_count == result.distinct_ccn_count == 3
    assert result.leading_zero_ccn_count == 1
    assert result.additive_fields == ("Synthetic Additive Note",)
    assert result.retry_count == 0
    assert not result.content_noop
    assert not result.manifest_noop
    assert result.manifest_path.read_bytes().endswith(b"\n")

    manifest = json.loads(result.manifest_path.read_bytes())
    assert result.manifest_path.read_bytes() == canonical_json_bytes(manifest)
    assert manifest["source"]["stable_dataset_id"] == STABLE_DATASET_ID
    assert manifest["source"]["metadata_url"] == METADATA_URL
    assert manifest["transport"] == {
        "mode": "full_csv",
        "page_count": 1,
        "record_count": 3,
    }
    assert manifest["reconciliation"]["distinct_ccn_count"] == 3
    assert manifest["schema"]["dictionary_sha256"] == DICTIONARY_SHA256
    assert manifest["storage"]["blob_path"] == (
        result.blob_path.relative_to(tmp_path / "raw").as_posix()
    )
    reconciled = load_and_reconcile_facility_snapshot(
        result.manifest_path,
        tmp_path / "raw",
    )
    assert reconciled.manifest.to_dict() == manifest


def test_html_and_unsupported_media_type_cannot_publish(tmp_path: Path) -> None:
    response = response_for_fixture(
        content=b"<html>error</html>",
        content_type="text/html",
    )

    with pytest.raises(FacilityCsvError, match="media type"):
        extract_cms_dialysis_facility(
            run_id="facility-html",
            output_root=tmp_path / "raw",
            json_loader=fixture_loader(),
            opener=SequenceOpener([response]),
            now=fixed_now,
        )

    assert not (tmp_path / "raw" / "blobs").exists()
    assert not (tmp_path / "raw" / "manifests").exists()


def test_truncated_transfer_cannot_publish(tmp_path: Path) -> None:
    complete = DOWNLOAD_PATH.read_bytes()
    truncated = complete[:100]
    response = FakeResponse(
        truncated,
        {
            "Content-Length": str(len(complete)),
            "Content-Type": "text/csv",
        },
    )

    with pytest.raises(Exception, match="Content-Length"):
        extract_cms_dialysis_facility(
            run_id="facility-truncated",
            output_root=tmp_path / "raw",
            json_loader=fixture_loader(),
            opener=SequenceOpener([response]),
            retry_policy=RetryPolicy(max_attempts=1),
            now=fixed_now,
        )

    assert not (tmp_path / "raw" / "blobs").exists()
    assert not (tmp_path / "raw" / "manifests").exists()


def test_same_content_new_run_reuses_verified_blob(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    first = extract_cms_dialysis_facility(
        run_id="facility-fixture-001",
        output_root=output_root,
        json_loader=fixture_loader(),
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )
    second = extract_cms_dialysis_facility(
        run_id="facility-fixture-002",
        output_root=output_root,
        json_loader=fixture_loader(),
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )

    assert second.status == "content_noop"
    assert second.content_noop
    assert second.blob_path == first.blob_path
    assert len(list((output_root / "blobs" / "sha256").glob("*.csv"))) == 1


def test_same_run_is_idempotent_but_different_lineage_conflicts(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "raw"
    first = extract_cms_dialysis_facility(
        run_id="facility-fixture-001",
        output_root=output_root,
        json_loader=fixture_loader(),
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )
    rerun = extract_cms_dialysis_facility(
        run_id="facility-fixture-001",
        output_root=output_root,
        json_loader=fixture_loader(),
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )
    assert rerun.status == "manifest_noop"
    assert rerun.manifest_noop

    with pytest.raises(FacilityManifestConflictError):
        extract_cms_dialysis_facility(
            run_id="facility-fixture-001",
            output_root=output_root,
            json_loader=fixture_loader(),
            opener=SequenceOpener([response_for_fixture()]),
            now=lambda: datetime(2026, 8, 15, 12, 1, tzinfo=UTC),
        )
    assert first.manifest_path.exists()


def test_corrupt_existing_blob_blocks_reuse(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    first = extract_cms_dialysis_facility(
        run_id="facility-fixture-001",
        output_root=output_root,
        json_loader=fixture_loader(),
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )
    first.blob_path.write_bytes(b"corrupt")

    with pytest.raises(FacilityManifestConflictError, match="blob"):
        extract_cms_dialysis_facility(
            run_id="facility-fixture-002",
            output_root=output_root,
            json_loader=fixture_loader(),
            opener=SequenceOpener([response_for_fixture()]),
            now=fixed_now,
        )


def test_manifest_hashes_reconcile_independently() -> None:
    content = DOWNLOAD_PATH.read_bytes()

    assert hashlib.sha256(content).hexdigest()
    assert len(download_header()) == len(set(download_header()))


def test_manifest_rejects_a_non_utc_retrieval_timestamp(tmp_path: Path) -> None:
    output_root = tmp_path / "raw"
    result = extract_cms_dialysis_facility(
        run_id="facility-fixture-001",
        output_root=output_root,
        json_loader=fixture_loader(),
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )
    payload = json.loads(result.manifest_path.read_bytes())
    payload["retrieval"]["retrieved_at_utc"] = "not-a-utc-timestamp"
    result.manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(FacilityManifestConflictError, match="UTC timestamp"):
        load_and_reconcile_facility_snapshot(result.manifest_path, output_root)


def test_run_and_manifest_paths_cannot_escape_the_raw_root(tmp_path: Path) -> None:
    def unexpected_loader(_url: str) -> dict[str, object]:
        raise AssertionError("invalid run ID reached source resolution")

    with pytest.raises(ValueError, match="run ID"):
        extract_cms_dialysis_facility(
            run_id="../escape",
            output_root=tmp_path / "raw",
            json_loader=unexpected_loader,
        )

    output_root = tmp_path / "safe-raw"
    result = extract_cms_dialysis_facility(
        run_id="facility-fixture-001",
        output_root=output_root,
        json_loader=fixture_loader(),
        opener=SequenceOpener([response_for_fixture()]),
        now=fixed_now,
    )
    payload = json.loads(result.manifest_path.read_bytes())
    payload["storage"]["blob_path"] = "../escape.csv"
    result.manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(FacilityManifestConflictError, match="blob path"):
        load_and_reconcile_facility_snapshot(result.manifest_path, output_root)
