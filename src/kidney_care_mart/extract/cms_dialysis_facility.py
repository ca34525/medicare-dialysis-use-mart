"""Immutable full-CSV extraction for the CMS Dialysis Facility listing.

The extractor resolves stable dataset ``23ew-n7w9`` from the official Provider
Data Catalog, validates the current API schema before downloading, preserves
the full CSV byte-for-byte, proves one textual CCN per row, and publishes a
content-addressed blob plus a canonical run manifest. It does no typing,
geography assignment, quality interpretation, or aggregation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import re
import shutil
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import unquote, urlsplit

from kidney_care_mart.contracts.cms_dialysis_facility import (
    CCN_CSV_HEADER,
    CONTRACT_VERSION,
    REQUIRED_FIELDS,
    SOURCE_ID,
    ApiField,
    validate_api_schema,
)
from kidney_care_mart.extract.http import (
    DEFAULT_RETRY_POLICY,
    Jitter,
    ResponseOpener,
    RetryPolicy,
    Sleep,
    fetch_json,
    stream_download,
)
from kidney_care_mart.extract.manifest import (
    canonical_json_bytes,
    canonical_json_sha256,
    validate_run_id,
)

STABLE_DATASET_ID: Final = "23ew-n7w9"
CATALOG_URL: Final = "https://data.cms.gov/provider-data/data.json"
METADATA_URL: Final = (
    "https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/"
    f"{STABLE_DATASET_ID}"
)
DATASTORE_SCHEMA_URL: Final = (
    "https://data.cms.gov/provider-data/api/1/datastore/query/"
    f"{STABLE_DATASET_ID}/0?limit=1&offset=0&count=true&results=true&"
    "schema=true&keys=true&format=json"
)
EXPECTED_TITLE: Final = "Dialysis Facility - Listing by Facility"
EXPECTED_LANDING_URL: Final = "https://data.cms.gov/provider-data/dataset/23ew-n7w9"
DICTIONARY_URL: Final = (
    "https://data.cms.gov/provider-data/sites/default/files/"
    "data_dictionaries/dialysis/DF_Data_Dictionary.pdf"
)
DICTIONARY_LOCAL_PATH: Final = (
    "docs/source-dictionaries/cms_dialysis_facility-2026-07.pdf"
)
SCHEMA_EVIDENCE_LOCAL_PATH: Final = (
    "docs/source-schemas/cms_dialysis_facility.schema.json"
)
DICTIONARY_BYTE_COUNT: Final = 1_199_186
DICTIONARY_SHA256: Final = (
    "64348a21e3c98b9cb5b915a2243fb3a54b452ca61943c8f9f1eadf7429176fa0"
)
SCHEMA_EVIDENCE_SHA256: Final = (
    "e87cf25487005a81c8af015b4256da6a0da4205a369c2406cb3ff9b399ceec0f"
)
EXTRACTOR_VERSION: Final = "0.1.0"
MANIFEST_FORMAT_VERSION: Final = 1
_SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
_CCN_PATTERN: Final = re.compile(r"^[0-9]{1,10}$", flags=re.ASCII)
_ALLOWED_CSV_MEDIA_TYPES: Final = frozenset(
    {"application/csv", "application/octet-stream", "text/csv"}
)

JsonLoader = Callable[[str], Mapping[str, Any]]
Now = Callable[[], datetime]


class CatalogResolutionError(RuntimeError):
    """The Provider Data Catalog did not resolve the intended full CSV."""


class FacilityMetadataError(RuntimeError):
    """Current Provider Data API metadata violates the raw contract."""


class FacilityCsvError(RuntimeError):
    """The complete CSV does not satisfy header, row, or CCN invariants."""


class FacilityManifestConflictError(RuntimeError):
    """Immutable facility manifest or blob evidence conflicts."""


@dataclass(frozen=True, slots=True)
class ResolvedFacilitySource:
    """Durable identity plus resolved current distribution lineage."""

    catalog_url: str
    metadata_url: str
    stable_dataset_id: str
    title: str
    landing_url: str
    dictionary_url: str
    modified_date: str | None
    source_release: str | None
    next_update_date: str | None
    download_url: str


@dataclass(frozen=True, slots=True)
class FacilityApiMetadata:
    """Ordered raw transport fields and current row-count evidence."""

    fields: tuple[ApiField, ...]
    expected_row_count: int
    schema_sha256: str
    additive_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FacilityCsvEvidence:
    """Evidence streamed from one complete local full CSV."""

    header: tuple[str, ...]
    row_count: int
    distinct_ccn_count: int
    leading_zero_ccn_count: int
    header_sha256: str
    additive_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FacilitySnapshotManifest:
    """Canonical lineage and reconciliation for one raw facility snapshot."""

    pipeline_run_id: str
    retrieved_at_utc: str
    resolved_csv_url: str
    source_release: str | None
    source_modified_date: str | None
    next_update_date: str | None
    http_etag: str | None
    http_last_modified: str | None
    content_sha256: str
    byte_count: int
    csv_row_count: int
    fields: tuple[ApiField, ...]
    schema_sha256: str
    header_sha256: str
    additive_fields: tuple[str, ...]
    distinct_ccn_count: int
    leading_zero_ccn_count: int
    blob_path: str
    content_noop: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_format_version": MANIFEST_FORMAT_VERSION,
            "pipeline": {
                "extractor_version": EXTRACTOR_VERSION,
                "run_id": self.pipeline_run_id,
            },
            "source": {
                "catalog_url": CATALOG_URL,
                "dictionary_url": DICTIONARY_URL,
                "landing_url": EXPECTED_LANDING_URL,
                "logical_source_id": SOURCE_ID,
                "metadata_url": METADATA_URL,
                "resolved_csv_url": self.resolved_csv_url,
                "stable_dataset_id": STABLE_DATASET_ID,
            },
            "retrieval": {
                "http_etag": self.http_etag,
                "http_last_modified": self.http_last_modified,
                "next_update_date": self.next_update_date,
                "retrieved_at_utc": self.retrieved_at_utc,
                "source_modified_date": self.source_modified_date,
                "source_release": self.source_release,
            },
            "content": {
                "byte_count": self.byte_count,
                "csv_row_count": self.csv_row_count,
                "sha256": self.content_sha256,
            },
            "transport": {
                "mode": "full_csv",
                "page_count": 1,
                "record_count": self.csv_row_count,
            },
            "schema": {
                "additive_fields": list(self.additive_fields),
                "compatible_drift_observations": [],
                "contract_schema_evidence_sha256": SCHEMA_EVIDENCE_SHA256,
                "contract_version": CONTRACT_VERSION,
                "dictionary_byte_count": DICTIONARY_BYTE_COUNT,
                "dictionary_sha256": DICTIONARY_SHA256,
                "fields": [
                    {
                        "api_field_name": field.api_field_name,
                        "csv_header": field.csv_header,
                        "declared_type": field.declared_type,
                    }
                    for field in self.fields
                ],
                "header_sha256": self.header_sha256,
                "schema_sha256": self.schema_sha256,
            },
            "reconciliation": {
                "ccn_header": CCN_CSV_HEADER,
                "distinct_ccn_count": self.distinct_ccn_count,
                "leading_zero_ccn_count": self.leading_zero_ccn_count,
            },
            "storage": {
                "blob_path": self.blob_path,
                "content_noop": self.content_noop,
            },
        }


@dataclass(frozen=True, slots=True)
class ReconciledFacilitySnapshot:
    """A canonical manifest whose referenced CSV was independently verified."""

    manifest: FacilitySnapshotManifest
    manifest_path: Path
    blob_path: Path
    csv_evidence: FacilityCsvEvidence


@dataclass(frozen=True, slots=True)
class FacilityExtractionResult:
    """Concise output returned to orchestration and the explicit live CLI."""

    status: str
    blob_path: Path
    manifest_path: Path
    content_sha256: str
    byte_count: int
    row_count: int
    distinct_ccn_count: int
    leading_zero_ccn_count: int
    schema_sha256: str
    header_sha256: str
    additive_fields: tuple[str, ...]
    retry_count: int
    content_noop: bool
    manifest_noop: bool


def _as_mapping(value: object, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FacilityMetadataError(f"{context} must be a JSON object")
    return value


def _as_sequence(value: object, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise FacilityMetadataError(f"{context} must be a JSON array")
    return value


def _optional_text(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise FacilityManifestConflictError(f"manifest {field} must be text or null")
    return value


def _official_csv_url(url: object) -> str:
    if not isinstance(url, str) or not url:
        raise CatalogResolutionError("current complete full CSV URL is missing")
    parsed = urlsplit(url)
    path = unquote(parsed.path)
    is_csv = path.casefold().endswith(".csv")
    is_official = parsed.scheme == "https" and parsed.hostname == "data.cms.gov"
    is_partial = any(
        marker in path.casefold() for marker in ("sample", "state", "national")
    )
    if not is_official or not is_csv or is_partial:
        raise CatalogResolutionError(
            "resolved resource is not the official current complete full CSV"
        )
    return url


def resolve_current_source(catalog: Mapping[str, Any]) -> ResolvedFacilitySource:
    """Resolve exactly stable dataset 23ew-n7w9 and one complete CSV."""
    raw_datasets = _as_sequence(catalog.get("dataset"), context="catalog dataset")
    datasets = [
        _as_mapping(item, context="catalog dataset item") for item in raw_datasets
    ]
    intended = [
        dataset
        for dataset in datasets
        if dataset.get("identifier") == STABLE_DATASET_ID
    ]
    if len(intended) != 1:
        raise CatalogResolutionError(
            "Provider Data Catalog must contain exactly one stable dataset match; "
            f"found {len(intended)}"
        )
    dataset = intended[0]
    if dataset.get("title") != EXPECTED_TITLE:
        raise CatalogResolutionError(
            "stable dataset title does not corroborate Listing by Facility"
        )
    if dataset.get("landingPage") != EXPECTED_LANDING_URL:
        raise CatalogResolutionError(
            "stable dataset landing page does not corroborate Listing by Facility"
        )
    if dataset.get("accessLevel") not in {None, "public"}:
        raise CatalogResolutionError("stable facility dataset is not public")

    distributions = [
        _as_mapping(item, context="dataset distribution")
        for item in _as_sequence(
            dataset.get("distribution"), context="dataset distribution"
        )
    ]
    csv_candidates = [
        distribution
        for distribution in distributions
        if str(distribution.get("mediaType", "")).casefold() == "text/csv"
    ]
    if len(csv_candidates) != 1:
        raise CatalogResolutionError(
            "stable facility dataset must expose exactly one complete full CSV; "
            f"found {len(csv_candidates)}"
        )
    distribution = csv_candidates[0]
    download_url = _official_csv_url(distribution.get("downloadURL"))
    dictionary_url = distribution.get("describedBy")
    if dictionary_url != DICTIONARY_URL:
        raise CatalogResolutionError(
            "full CSV does not reference the supported official facility dictionary"
        )

    def text_or_none(name: str) -> str | None:
        value = dataset.get(name)
        return value if isinstance(value, str) else None

    return ResolvedFacilitySource(
        catalog_url=CATALOG_URL,
        metadata_url=METADATA_URL,
        stable_dataset_id=STABLE_DATASET_ID,
        title=EXPECTED_TITLE,
        landing_url=EXPECTED_LANDING_URL,
        dictionary_url=DICTIONARY_URL,
        modified_date=text_or_none("modified"),
        source_release=text_or_none("released"),
        next_update_date=text_or_none("nextUpdateDate"),
        download_url=download_url,
    )


def _api_schema_sha256(fields: Sequence[ApiField]) -> str:
    return canonical_json_sha256(
        [
            {
                "api_field_name": field.api_field_name,
                "csv_header": field.csv_header,
                "declared_type": field.declared_type,
            }
            for field in fields
        ]
    )


def parse_api_metadata(payload: Mapping[str, Any]) -> FacilityApiMetadata:
    """Parse one current Provider Data API schema and contract-check it."""
    count = payload.get("count")
    if type(count) is not int or count < 0:
        raise FacilityMetadataError("Provider Data API count must be nonnegative")
    schema = _as_mapping(payload.get("schema"), context="API schema")
    if len(schema) != 1:
        raise FacilityMetadataError(
            "Provider Data API schema must contain exactly one resource"
        )
    resource = _as_mapping(next(iter(schema.values())), context="API resource schema")
    raw_fields = _as_mapping(resource.get("fields"), context="API fields")
    fields: list[ApiField] = []
    for api_name, raw_field in raw_fields.items():
        if not isinstance(api_name, str) or not api_name:
            raise FacilityMetadataError("API field names must be nonblank text")
        field = _as_mapping(raw_field, context=f"API field {api_name}")
        description = field.get("description")
        declared_type = field.get("type")
        if not isinstance(description, str) or not description:
            raise FacilityMetadataError(
                f"API field {api_name} has no full-CSV description"
            )
        if not isinstance(declared_type, str) or not declared_type:
            raise FacilityMetadataError(f"API field {api_name} has no type")
        fields.append(
            ApiField(
                api_field_name=api_name,
                csv_header=description,
                declared_type=declared_type,
            )
        )
    result = validate_api_schema(fields)
    if not result.is_valid:
        raise FacilityMetadataError(
            "facility API schema violates the raw contract: "
            + "; ".join(issue.message for issue in result.issues)
        )
    return FacilityApiMetadata(
        fields=tuple(fields),
        expected_row_count=count,
        schema_sha256=_api_schema_sha256(fields),
        additive_fields=result.additive_fields,
    )


def _header_sha256(header: Sequence[str]) -> str:
    return canonical_json_sha256(list(header))


def validate_facility_csv(
    path: Path,
    metadata_fields: Sequence[ApiField],
    *,
    expected_row_count: int | None = None,
) -> FacilityCsvEvidence:
    """Stream the full CSV and prove ordered headers plus one CCN per row."""
    if expected_row_count is not None and expected_row_count < 0:
        raise ValueError("expected_row_count cannot be negative")
    fields = tuple(metadata_fields)
    metadata_headers = tuple(field.csv_header for field in fields)
    duplicate_metadata = sorted(
        header for header, count in Counter(metadata_headers).items() if count > 1
    )
    if duplicate_metadata:
        raise FacilityCsvError(
            "Provider Data metadata contains duplicate CSV headers: "
            + ", ".join(duplicate_metadata)
        )
    contract = validate_api_schema(fields)
    if not contract.is_valid:
        raise FacilityCsvError(
            "Provider Data metadata violates the facility contract: "
            + "; ".join(issue.message for issue in contract.issues)
        )

    try:
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.reader(source, strict=True)
            try:
                raw_header = next(reader)
            except StopIteration as error:
                raise FacilityCsvError("facility CSV is empty") from error
            duplicate_header = sorted(
                header for header, count in Counter(raw_header).items() if count > 1
            )
            if duplicate_header:
                raise FacilityCsvError(
                    "facility CSV contains duplicate headers: "
                    + ", ".join(duplicate_header)
                )
            header = tuple(raw_header)
            if header != metadata_headers:
                raise FacilityCsvError(
                    "facility CSV header does not match ordered Provider Data metadata"
                )
            try:
                ccn_index = header.index(CCN_CSV_HEADER)
            except ValueError as error:
                raise FacilityCsvError(
                    "facility CSV has no governed CCN header"
                ) from error

            first_row_by_ccn: dict[str, int] = {}
            leading_zero_count = 0
            row_count = 0
            for row in reader:
                row_count += 1
                if len(row) != len(header):
                    raise FacilityCsvError(
                        f"CSV row {reader.line_num} has {len(row)} values; "
                        f"expected {len(header)}"
                    )
                ccn = row[ccn_index]
                if not ccn.strip():
                    raise FacilityCsvError(
                        f"CCN is blank at source row {reader.line_num}"
                    )
                if _CCN_PATTERN.fullmatch(ccn) is None:
                    raise FacilityCsvError(
                        "CCN must be 1-10 ASCII-digit text at source row "
                        f"{reader.line_num}: {ccn!r}"
                    )
                first_row = first_row_by_ccn.setdefault(ccn, reader.line_num)
                if first_row != reader.line_num:
                    raise FacilityCsvError(
                        f"duplicate CCN {ccn!r} at row {reader.line_num}; "
                        f"first seen at row {first_row}"
                    )
                if ccn.startswith("0"):
                    leading_zero_count += 1
    except UnicodeDecodeError as error:
        raise FacilityCsvError("facility CSV is not valid UTF-8") from error
    except csv.Error as error:
        raise FacilityCsvError(f"facility CSV parsing failed: {error}") from error

    if expected_row_count is not None and row_count != expected_row_count:
        raise FacilityCsvError(
            "facility CSV row count does not reconcile to Provider Data metadata: "
            f"expected {expected_row_count}, found {row_count}"
        )
    distinct_count = len(first_row_by_ccn)
    if row_count != distinct_count:
        raise FacilityCsvError(
            "facility CSV row count does not equal distinct nonblank CCN count"
        )
    return FacilityCsvEvidence(
        header=header,
        row_count=row_count,
        distinct_ccn_count=distinct_count,
        leading_zero_ccn_count=leading_zero_count,
        header_sha256=_header_sha256(header),
        additive_fields=contract.additive_fields,
    )


def _utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now() must return a timezone-aware datetime")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("rb") as source:
        while chunk := source.read(64 * 1024):
            digest.update(chunk)
            byte_count += len(chunk)
    return digest.hexdigest(), byte_count


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _verify_dictionary(path: Path | None = None) -> None:
    dictionary_path = path or (_repository_root() / DICTIONARY_LOCAL_PATH)
    actual_hash, actual_bytes = _hash_file(dictionary_path)
    if actual_bytes != DICTIONARY_BYTE_COUNT or actual_hash != DICTIONARY_SHA256:
        raise FacilityMetadataError(
            "pinned facility dictionary does not match recorded byte/hash evidence"
        )


def verify_schema_evidence(path: Path | None = None) -> None:
    """Reparse the committed normalized schema and verify its semantic hash."""
    schema_path = path or (_repository_root() / SCHEMA_EVIDENCE_LOCAL_PATH)
    try:
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FacilityMetadataError(
            "cannot parse committed facility schema evidence"
        ) from error
    if not isinstance(payload, Mapping):
        raise FacilityMetadataError("facility schema evidence must be a JSON object")
    hash_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"retrieval", "schema_sha256"}
    }
    observed_hash = payload.get("schema_sha256")
    calculated_hash = canonical_json_sha256(hash_payload)
    if (
        observed_hash != SCHEMA_EVIDENCE_SHA256
        or calculated_hash != SCHEMA_EVIDENCE_SHA256
    ):
        raise FacilityMetadataError(
            "committed facility schema evidence hash does not reconcile"
        )
    if payload.get("source_id") != SOURCE_ID:
        raise FacilityMetadataError("facility schema evidence source is incompatible")
    if payload.get("contract_version") != CONTRACT_VERSION:
        raise FacilityMetadataError(
            "facility schema evidence contract version is incompatible"
        )
    if payload.get("required_semantic_mapping") != [
        asdict(field) for field in REQUIRED_FIELDS
    ]:
        raise FacilityMetadataError(
            "facility schema evidence required mapping does not reconcile"
        )
    dictionary = payload.get("dictionary")
    if not isinstance(dictionary, Mapping) or (
        dictionary.get("local_path") != DICTIONARY_LOCAL_PATH
        or dictionary.get("byte_count") != DICTIONARY_BYTE_COUNT
        or dictionary.get("sha256") != DICTIONARY_SHA256
    ):
        raise FacilityMetadataError(
            "facility schema evidence dictionary lineage does not reconcile"
        )


def _validate_media_type(content_type: str | None) -> None:
    media_type = (content_type or "").split(";", 1)[0].strip().casefold()
    if media_type not in _ALLOWED_CSV_MEDIA_TYPES:
        raise FacilityCsvError(
            f"facility download has unsupported media type: {content_type!r}"
        )


def _validate_manifest(manifest: FacilitySnapshotManifest) -> None:
    validate_run_id(manifest.pipeline_run_id)
    try:
        parsed_retrieval = datetime.fromisoformat(
            manifest.retrieved_at_utc.removesuffix("Z") + "+00:00"
        )
    except ValueError as error:
        raise FacilityManifestConflictError(
            "manifest retrieval time must be a canonical UTC timestamp"
        ) from error
    if _utc_timestamp(parsed_retrieval) != manifest.retrieved_at_utc:
        raise FacilityManifestConflictError(
            "manifest retrieval time must be a canonical UTC timestamp"
        )
    if _SHA256_PATTERN.fullmatch(manifest.content_sha256) is None:
        raise FacilityManifestConflictError("manifest content SHA-256 is invalid")
    expected_blob_path = (
        PurePosixPath("blobs") / "sha256" / f"{manifest.content_sha256}.csv"
    ).as_posix()
    if manifest.blob_path != expected_blob_path:
        raise FacilityManifestConflictError(
            "manifest blob path does not match its content SHA-256"
        )
    if manifest.csv_row_count != manifest.distinct_ccn_count:
        raise FacilityManifestConflictError("manifest rows do not equal distinct CCNs")
    if not 0 <= manifest.leading_zero_ccn_count <= manifest.distinct_ccn_count:
        raise FacilityManifestConflictError(
            "manifest leading-zero count is outside the CCN population"
        )
    if _api_schema_sha256(manifest.fields) != manifest.schema_sha256:
        raise FacilityManifestConflictError("manifest schema hash does not reconcile")
    contract = validate_api_schema(manifest.fields)
    if not contract.is_valid or contract.additive_fields != manifest.additive_fields:
        raise FacilityManifestConflictError(
            "manifest API schema does not reconcile to the facility contract"
        )
    if tuple(sorted(manifest.additive_fields)) != manifest.additive_fields:
        raise FacilityManifestConflictError("manifest additive fields are not sorted")


def _manifest_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FacilityManifestConflictError(f"manifest {field} must be an object")
    return value


def _manifest_integer(value: object, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise FacilityManifestConflictError(
            f"manifest {field} must be a nonnegative integer"
        )
    return value


def facility_manifest_from_payload(
    payload: Mapping[str, Any],
) -> FacilitySnapshotManifest:
    """Parse and strictly validate a canonical facility manifest payload."""
    if payload.get("manifest_format_version") != MANIFEST_FORMAT_VERSION:
        raise FacilityManifestConflictError("unsupported facility manifest version")
    pipeline = _manifest_mapping(payload.get("pipeline"), field="pipeline")
    source = _manifest_mapping(payload.get("source"), field="source")
    retrieval = _manifest_mapping(payload.get("retrieval"), field="retrieval")
    content = _manifest_mapping(payload.get("content"), field="content")
    transport = _manifest_mapping(payload.get("transport"), field="transport")
    schema = _manifest_mapping(payload.get("schema"), field="schema")
    reconciliation = _manifest_mapping(
        payload.get("reconciliation"), field="reconciliation"
    )
    storage = _manifest_mapping(payload.get("storage"), field="storage")

    expected_source = {
        "catalog_url": CATALOG_URL,
        "dictionary_url": DICTIONARY_URL,
        "landing_url": EXPECTED_LANDING_URL,
        "logical_source_id": SOURCE_ID,
        "metadata_url": METADATA_URL,
        "stable_dataset_id": STABLE_DATASET_ID,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise FacilityManifestConflictError(
                f"manifest source identity is incompatible: {key}"
            )
    resolved_csv_url = _official_csv_url(source.get("resolved_csv_url"))
    if pipeline.get("extractor_version") != EXTRACTOR_VERSION:
        raise FacilityManifestConflictError("unsupported facility extractor version")
    if transport != {
        "mode": "full_csv",
        "page_count": 1,
        "record_count": content.get("csv_row_count"),
    }:
        raise FacilityManifestConflictError("manifest full-CSV transport is invalid")
    if schema.get("contract_version") != CONTRACT_VERSION:
        raise FacilityManifestConflictError("unsupported facility contract version")
    if schema.get("contract_schema_evidence_sha256") != SCHEMA_EVIDENCE_SHA256:
        raise FacilityManifestConflictError("unsupported schema evidence hash")
    if schema.get("dictionary_byte_count") != DICTIONARY_BYTE_COUNT:
        raise FacilityManifestConflictError("dictionary byte evidence does not match")
    if schema.get("dictionary_sha256") != DICTIONARY_SHA256:
        raise FacilityManifestConflictError("dictionary hash evidence does not match")
    if schema.get("compatible_drift_observations") != []:
        raise FacilityManifestConflictError(
            "unsupported facility compatible-drift observations"
        )

    raw_fields = schema.get("fields")
    if not isinstance(raw_fields, list):
        raise FacilityManifestConflictError("manifest schema fields must be an array")
    fields: list[ApiField] = []
    for index, value in enumerate(raw_fields):
        raw = _manifest_mapping(value, field=f"schema.fields[{index}]")
        try:
            fields.append(
                ApiField(
                    api_field_name=str(raw["api_field_name"]),
                    csv_header=str(raw["csv_header"]),
                    declared_type=str(raw["declared_type"]),
                )
            )
        except KeyError as error:
            raise FacilityManifestConflictError(
                f"manifest schema field is missing {error.args[0]}"
            ) from error
    additive = schema.get("additive_fields")
    if not isinstance(additive, list) or not all(
        isinstance(value, str) for value in additive
    ):
        raise FacilityManifestConflictError(
            "manifest additive fields must be a text array"
        )
    content_noop = storage.get("content_noop")
    if type(content_noop) is not bool:
        raise FacilityManifestConflictError("manifest content_noop must be boolean")
    run_id = pipeline.get("run_id")
    if not isinstance(run_id, str):
        raise FacilityManifestConflictError("manifest run ID must be text")
    retrieved = retrieval.get("retrieved_at_utc")
    if not isinstance(retrieved, str):
        raise FacilityManifestConflictError("manifest retrieval timestamp must be text")
    content_hash = content.get("sha256")
    if not isinstance(content_hash, str):
        raise FacilityManifestConflictError("manifest content hash must be text")
    schema_hash = schema.get("schema_sha256")
    header_hash = schema.get("header_sha256")
    blob_path = storage.get("blob_path")
    if not all(
        isinstance(value, str) for value in (schema_hash, header_hash, blob_path)
    ):
        raise FacilityManifestConflictError("manifest hash/path evidence must be text")

    manifest = FacilitySnapshotManifest(
        pipeline_run_id=run_id,
        retrieved_at_utc=retrieved,
        resolved_csv_url=resolved_csv_url,
        source_release=_optional_text(
            retrieval.get("source_release"), field="retrieval.source_release"
        ),
        source_modified_date=_optional_text(
            retrieval.get("source_modified_date"),
            field="retrieval.source_modified_date",
        ),
        next_update_date=_optional_text(
            retrieval.get("next_update_date"), field="retrieval.next_update_date"
        ),
        http_etag=_optional_text(
            retrieval.get("http_etag"), field="retrieval.http_etag"
        ),
        http_last_modified=_optional_text(
            retrieval.get("http_last_modified"),
            field="retrieval.http_last_modified",
        ),
        content_sha256=content_hash,
        byte_count=_manifest_integer(
            content.get("byte_count"), field="content.byte_count"
        ),
        csv_row_count=_manifest_integer(
            content.get("csv_row_count"), field="content.csv_row_count"
        ),
        fields=tuple(fields),
        schema_sha256=schema_hash,
        header_sha256=header_hash,
        additive_fields=tuple(additive),
        distinct_ccn_count=_manifest_integer(
            reconciliation.get("distinct_ccn_count"),
            field="reconciliation.distinct_ccn_count",
        ),
        leading_zero_ccn_count=_manifest_integer(
            reconciliation.get("leading_zero_ccn_count"),
            field="reconciliation.leading_zero_ccn_count",
        ),
        blob_path=blob_path,
        content_noop=content_noop,
    )
    if reconciliation.get("ccn_header") != CCN_CSV_HEADER:
        raise FacilityManifestConflictError("manifest CCN header is incompatible")
    _validate_manifest(manifest)
    if payload != manifest.to_dict():
        raise FacilityManifestConflictError(
            "manifest contains unsupported or inconsistent fields"
        )
    return manifest


def _resolve_blob(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise FacilityManifestConflictError("manifest blob path escapes raw root")
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root.resolve()):
        raise FacilityManifestConflictError("manifest blob path escapes raw root")
    return path


def _reconcile_blob(
    manifest: FacilitySnapshotManifest,
    blob_path: Path,
) -> FacilityCsvEvidence:
    try:
        actual_hash, actual_bytes = _hash_file(blob_path)
    except OSError as error:
        raise FacilityManifestConflictError(
            f"cannot read facility blob: {blob_path}"
        ) from error
    if actual_hash != manifest.content_sha256 or actual_bytes != manifest.byte_count:
        raise FacilityManifestConflictError(
            "facility blob byte/hash evidence does not reconcile"
        )
    evidence = validate_facility_csv(
        blob_path,
        manifest.fields,
        expected_row_count=manifest.csv_row_count,
    )
    if (
        evidence.header_sha256 != manifest.header_sha256
        or evidence.additive_fields != manifest.additive_fields
        or evidence.distinct_ccn_count != manifest.distinct_ccn_count
        or evidence.leading_zero_ccn_count != manifest.leading_zero_ccn_count
    ):
        raise FacilityManifestConflictError(
            "facility blob schema or CCN evidence does not reconcile"
        )
    return evidence


def load_and_reconcile_facility_snapshot(
    manifest_path: Path,
    raw_root: Path,
) -> ReconciledFacilitySnapshot:
    """Load a canonical manifest and independently reverify its exact CSV."""
    try:
        _verify_dictionary()
        verify_schema_evidence()
    except (FacilityMetadataError, OSError) as error:
        raise FacilityManifestConflictError(
            "committed facility contract evidence does not reconcile"
        ) from error
    root = raw_root.resolve()
    resolved_manifest = manifest_path.resolve()
    expected_root = (root / "manifests" / SOURCE_ID).resolve()
    if not resolved_manifest.is_relative_to(expected_root):
        raise FacilityManifestConflictError(
            "facility manifest path must remain beneath its source directory"
        )
    try:
        manifest_bytes = resolved_manifest.read_bytes()
        payload = json.loads(manifest_bytes)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FacilityManifestConflictError("cannot parse facility manifest") from error
    if not isinstance(payload, Mapping):
        raise FacilityManifestConflictError("facility manifest must be an object")
    if canonical_json_bytes(payload) != manifest_bytes:
        raise FacilityManifestConflictError("facility manifest is not canonical JSON")
    manifest = facility_manifest_from_payload(payload)
    blob_path = _resolve_blob(root, manifest.blob_path)
    evidence = _reconcile_blob(manifest, blob_path)
    return ReconciledFacilitySnapshot(
        manifest=manifest,
        manifest_path=resolved_manifest,
        blob_path=blob_path,
        csv_evidence=evidence,
    )


def _write_atomic_new(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    if temporary.exists():
        raise FacilityManifestConflictError(
            f"facility manifest staging path already exists: {temporary}"
        )
    try:
        with temporary.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise FacilityManifestConflictError(
                f"facility manifest appeared concurrently: {path}"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _publish_snapshot(
    *,
    staged_path: Path,
    root: Path,
    manifest: FacilitySnapshotManifest,
) -> tuple[FacilitySnapshotManifest, Path, Path, bool]:
    _validate_manifest(manifest)
    resolved_root = root.resolve()
    staged = staged_path.resolve()
    if not staged.is_relative_to(resolved_root):
        raise FacilityManifestConflictError(
            "facility staged file must remain on the configured raw volume"
        )
    _reconcile_blob(manifest, staged)
    blob_path = _resolve_blob(resolved_root, manifest.blob_path)
    manifest_path = (
        resolved_root / "manifests" / SOURCE_ID / f"{manifest.pipeline_run_id}.json"
    )
    if manifest_path.exists():
        existing_bytes = manifest_path.read_bytes()
        try:
            payload = json.loads(existing_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise FacilityManifestConflictError(
                f"existing facility manifest is invalid: {manifest_path}"
            ) from error
        if not isinstance(payload, Mapping):
            raise FacilityManifestConflictError("existing manifest is not an object")
        existing = facility_manifest_from_payload(payload)
        if canonical_json_bytes(payload) != existing_bytes:
            raise FacilityManifestConflictError("existing manifest is not canonical")
        candidate = replace(manifest, content_noop=existing.content_noop)
        if existing != candidate:
            raise FacilityManifestConflictError(
                "facility run ID already exists with different content or lineage"
            )
        _reconcile_blob(candidate, blob_path)
        staged.unlink(missing_ok=True)
        return candidate, manifest_path, blob_path, True

    content_noop = blob_path.exists()
    final_manifest = replace(manifest, content_noop=content_noop)
    if content_noop:
        _reconcile_blob(final_manifest, blob_path)
    else:
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(staged, blob_path)
        except FileExistsError:
            final_manifest = replace(manifest, content_noop=True)
        _reconcile_blob(final_manifest, blob_path)
    staged.unlink(missing_ok=True)
    _write_atomic_new(manifest_path, canonical_json_bytes(final_manifest.to_dict()))
    return final_manifest, manifest_path, blob_path, False


def extract_cms_dialysis_facility(
    *,
    run_id: str,
    output_root: Path,
    json_loader: JsonLoader = fetch_json,
    opener: ResponseOpener | None = None,
    sleep: Sleep = time.sleep,
    jitter: Jitter = random.random,
    now: Now = _utc_now,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    dictionary_path: Path | None = None,
) -> FacilityExtractionResult:
    """Resolve, validate, and publish one complete immutable facility CSV."""
    validate_run_id(run_id)
    _verify_dictionary(dictionary_path)
    verify_schema_evidence()
    resolved = resolve_current_source(json_loader(CATALOG_URL))
    metadata = parse_api_metadata(json_loader(DATASTORE_SCHEMA_URL))

    root = output_root.resolve()
    temporary_directory = root / ".tmp" / run_id
    temporary_directory.mkdir(parents=True, exist_ok=False)
    staged_path = temporary_directory / "download.csv.partial"
    download_kwargs: dict[str, Any] = {
        "sleep": sleep,
        "jitter": jitter,
        "retry_policy": retry_policy,
    }
    if opener is not None:
        download_kwargs["opener"] = opener
    try:
        download = stream_download(
            resolved.download_url,
            staged_path,
            **download_kwargs,
        )
        _validate_media_type(download.content_type)
        evidence = validate_facility_csv(
            staged_path,
            metadata.fields,
            expected_row_count=metadata.expected_row_count,
        )
        manifest = FacilitySnapshotManifest(
            pipeline_run_id=run_id,
            retrieved_at_utc=_utc_timestamp(now()),
            resolved_csv_url=resolved.download_url,
            source_release=resolved.source_release,
            source_modified_date=resolved.modified_date,
            next_update_date=resolved.next_update_date,
            http_etag=download.etag,
            http_last_modified=download.last_modified,
            content_sha256=download.content_sha256,
            byte_count=download.byte_count,
            csv_row_count=evidence.row_count,
            fields=metadata.fields,
            schema_sha256=metadata.schema_sha256,
            header_sha256=evidence.header_sha256,
            additive_fields=evidence.additive_fields,
            distinct_ccn_count=evidence.distinct_ccn_count,
            leading_zero_ccn_count=evidence.leading_zero_ccn_count,
            blob_path=f"blobs/sha256/{download.content_sha256}.csv",
        )
        final_manifest, manifest_path, blob_path, manifest_noop = _publish_snapshot(
            staged_path=staged_path,
            root=root,
            manifest=manifest,
        )
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)

    status = "published"
    if manifest_noop:
        status = "manifest_noop"
    elif final_manifest.content_noop:
        status = "content_noop"
    return FacilityExtractionResult(
        status=status,
        blob_path=blob_path,
        manifest_path=manifest_path,
        content_sha256=final_manifest.content_sha256,
        byte_count=final_manifest.byte_count,
        row_count=final_manifest.csv_row_count,
        distinct_ccn_count=final_manifest.distinct_ccn_count,
        leading_zero_ccn_count=final_manifest.leading_zero_ccn_count,
        schema_sha256=final_manifest.schema_sha256,
        header_sha256=final_manifest.header_sha256,
        additive_fields=final_manifest.additive_fields,
        retry_count=download.retry_count,
        content_noop=final_manifest.content_noop,
        manifest_noop=manifest_noop,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve and extract the current official CMS Dialysis Facility "
            "Listing full CSV. This command performs live requests."
        )
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit live command and print non-row-level evidence."""
    arguments = _parser().parse_args(argv)
    try:
        result = extract_cms_dialysis_facility(
            run_id=arguments.run_id,
            output_root=arguments.output_root,
        )
    except (RuntimeError, OSError, ValueError) as error:
        print(f"cms_dialysis_facility extraction failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "additive_field_count": len(result.additive_fields),
                "blob_path": str(result.blob_path),
                "byte_count": result.byte_count,
                "content_noop": result.content_noop,
                "content_sha256": result.content_sha256,
                "distinct_ccn_count": result.distinct_ccn_count,
                "header_sha256": result.header_sha256,
                "leading_zero_ccn_count": result.leading_zero_ccn_count,
                "manifest_noop": result.manifest_noop,
                "manifest_path": str(result.manifest_path),
                "retry_count": result.retry_count,
                "row_count": result.row_count,
                "schema_sha256": result.schema_sha256,
                "status": result.status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
