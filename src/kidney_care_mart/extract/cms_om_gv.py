"""CMS Original Medicare Geographic Variation full-file extraction.

This module resolves the current official CSV from durable CMS metadata. It
does not type metrics, normalize missingness, or filter source rows.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote, urljoin, urlsplit

from kidney_care_mart.contracts.cms_om_gv import (
    CONTRACT_VERSION,
    SOURCE_ID,
    ColumnSchema,
    validate_schema,
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
    CsvValidationError,
    SnapshotManifest,
    header_sha256,
    publish_snapshot,
    schema_sha256,
    validate_raw_csv,
    validate_run_id,
)

STABLE_DATASET_ID: Final = "6219697b-8f6c-4164-bed4-cd9317c58ebc"
CATALOG_URL: Final = "https://data.cms.gov/data.json"
EXPECTED_LANDING_URL: Final = (
    "https://data.cms.gov/summary-statistics-on-use-and-payments/"
    "medicare-geographic-comparisons/"
    "medicare-geographic-variation-by-national-state-county"
)
EXPECTED_TITLE: Final = "Medicare Geographic Variation - by National, State & County"
DATA_VIEWER_URL: Final = (
    "https://data.cms.gov/data-api/v1/dataset/"
    f"{STABLE_DATASET_ID}/data-viewer?size=1&offset=0"
)
EXTRACTOR_VERSION: Final = "0.1.0"
_DATASET_ID_PATTERN: Final = re.compile(
    r"/dataset/([0-9a-fA-F-]{36})/(?:data|data-viewer)(?:$|[/?])"
)
_RELEASE_PATTERN: Final = re.compile(r"\b(20[0-9]{2})-(20[0-9]{2})\b")

JsonLoader = Callable[[str], Mapping[str, Any]]
Now = Callable[[], datetime]


class CatalogResolutionError(RuntimeError):
    """The durable CMS catalog did not resolve one intended full CSV."""


class CmsMetadataError(RuntimeError):
    """Current CMS data-viewer metadata is incomplete or incompatible."""


@dataclass(frozen=True, slots=True)
class ResolvedCmsSource:
    """Durable and version-specific lineage resolved from the CMS catalog."""

    catalog_url: str
    stable_dataset_id: str
    title: str
    landing_url: str
    modified_date: str | None
    source_release: str | None
    download_url: str
    data_viewer_url: str


@dataclass(frozen=True, slots=True)
class CmsDataViewerMetadata:
    """Ordered current CMS schema and full-file reconciliation evidence."""

    columns: tuple[ColumnSchema, ...]
    expected_row_count: int
    expected_byte_count: int
    expected_sha1: str | None
    data_file_name: str
    source_release: str | None
    cms_table_schema_hash: str | None


@dataclass(frozen=True, slots=True)
class CmsExtractionResult:
    """Structured outcome returned to orchestration and the live CLI."""

    status: str
    blob_path: Path
    manifest_path: Path
    content_sha256: str
    byte_count: int
    row_count: int
    additive_columns: tuple[str, ...]
    retry_count: int
    content_noop: bool
    manifest_noop: bool


def _dataset_id(dataset: Mapping[str, Any]) -> str | None:
    identifier = dataset.get("identifier")
    if not isinstance(identifier, str):
        return None
    match = _DATASET_ID_PATTERN.search(identifier)
    return match.group(1).lower() if match else None


def _as_mapping(value: object, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CatalogResolutionError(f"{context} must be a JSON object")
    return value


def _is_csv_distribution(distribution: Mapping[str, Any]) -> bool:
    media_type = str(distribution.get("mediaType", "")).casefold()
    source_format = str(distribution.get("format", "")).casefold()
    return media_type == "text/csv" or source_format == "csv"


def _validate_official_csv_url(url: str) -> None:
    parsed = urlsplit(url)
    is_official = (
        parsed.scheme == "https"
        and parsed.hostname == "data.cms.gov"
        and unquote(parsed.path).casefold().endswith(".csv")
    )
    if not is_official:
        raise CatalogResolutionError(
            "resolved full CSV is not an official CMS HTTPS CSV URL"
        )
    if "sample" in unquote(parsed.path).casefold():
        raise CatalogResolutionError(
            "resolved CSV appears to be a sample, not a full file"
        )


def resolve_current_source(catalog: Mapping[str, Any]) -> ResolvedCmsSource:
    """Resolve exactly one intended CMS dataset and its one current full CSV."""
    raw_datasets = catalog.get("dataset")
    if not isinstance(raw_datasets, Sequence) or isinstance(raw_datasets, (str, bytes)):
        raise CatalogResolutionError("CMS catalog dataset collection is missing")
    datasets = [
        _as_mapping(item, context="CMS catalog dataset") for item in raw_datasets
    ]
    intended = [
        dataset for dataset in datasets if _dataset_id(dataset) == STABLE_DATASET_ID
    ]
    if len(intended) != 1:
        raise CatalogResolutionError(
            "CMS catalog must contain exactly one stable dataset match; "
            f"found {len(intended)}"
        )

    dataset = intended[0]
    if dataset.get("title") != EXPECTED_TITLE:
        raise CatalogResolutionError(
            "stable CMS dataset title does not corroborate the intended source"
        )
    if dataset.get("landingPage") != EXPECTED_LANDING_URL:
        raise CatalogResolutionError(
            "stable CMS dataset landing page does not corroborate the intended source"
        )

    raw_distributions = dataset.get("distribution")
    if not isinstance(raw_distributions, Sequence) or isinstance(
        raw_distributions, (str, bytes)
    ):
        raise CatalogResolutionError("stable CMS dataset has no distributions")
    distributions = [
        _as_mapping(item, context="CMS distribution") for item in raw_distributions
    ]
    csv_distributions = [item for item in distributions if _is_csv_distribution(item)]
    if len(csv_distributions) != 1:
        raise CatalogResolutionError(
            "stable CMS dataset must expose exactly one current full CSV; "
            f"found {len(csv_distributions)}"
        )
    distribution = csv_distributions[0]
    download_url = distribution.get("downloadURL")
    if not isinstance(download_url, str) or not download_url:
        raise CatalogResolutionError("current full CSV has no download URL")
    _validate_official_csv_url(download_url)

    modified_date = dataset.get("modified")
    source_release = dataset.get("temporal")
    return ResolvedCmsSource(
        catalog_url=CATALOG_URL,
        stable_dataset_id=STABLE_DATASET_ID,
        title=EXPECTED_TITLE,
        landing_url=EXPECTED_LANDING_URL,
        modified_date=modified_date if isinstance(modified_date, str) else None,
        source_release=source_release if isinstance(source_release, str) else None,
        download_url=download_url,
        data_viewer_url=DATA_VIEWER_URL,
    )


def _metadata_error(message: str) -> CmsMetadataError:
    return CmsMetadataError(f"CMS data-viewer metadata {message}")


def _nonnegative_int(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise _metadata_error(f"field {field} must be a nonnegative integer")
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise _metadata_error(f"field {field} must be a nonnegative integer") from error
    if parsed < 0:
        raise _metadata_error(f"field {field} must be a nonnegative integer")
    return parsed


def _normalized_url(url: str) -> tuple[str, str, str, str]:
    parsed = urlsplit(url)
    return (
        parsed.scheme.casefold(),
        (parsed.hostname or "").casefold(),
        unquote(parsed.path),
        parsed.query,
    )


def parse_data_viewer_metadata(
    payload: Mapping[str, Any],
    resolved: ResolvedCmsSource,
) -> CmsDataViewerMetadata:
    """Validate current data-viewer metadata before downloading any bytes."""
    meta = payload.get("meta")
    if not isinstance(meta, Mapping) or meta.get("success") is not True:
        raise _metadata_error("did not report success")

    raw_headers = meta.get("headers")
    if not isinstance(raw_headers, Sequence) or isinstance(raw_headers, (str, bytes)):
        raise _metadata_error("headers are missing")
    headers = tuple(raw_headers)
    if not all(isinstance(name, str) and name for name in headers):
        raise _metadata_error("headers must be nonblank strings")
    if len(headers) != len(set(headers)):
        raise _metadata_error("contains duplicate headers")

    file_metadata = meta.get("data_file_meta_data")
    if not isinstance(file_metadata, Mapping):
        raise _metadata_error("file evidence is missing")
    raw_types = file_metadata.get("csvColumnTypes")
    if not isinstance(raw_types, Mapping):
        raise _metadata_error("column types are missing")
    if set(raw_types) != set(headers):
        raise _metadata_error("column types do not reconcile to ordered headers")
    if not all(isinstance(raw_types[name], str) for name in headers):
        raise _metadata_error("column types must be strings")
    columns = tuple(
        ColumnSchema(name=name, declared_type=str(raw_types[name])) for name in headers
    )
    contract_result = validate_schema(columns)
    if not contract_result.is_valid:
        messages = "; ".join(issue.message for issue in contract_result.issues)
        raise _metadata_error(f"violates the required contract: {messages}")

    data_file_url = meta.get("data_file_url")
    if not isinstance(data_file_url, str) or not data_file_url:
        raise _metadata_error("download URL is missing")
    absolute_data_file_url = urljoin("https://data.cms.gov/", data_file_url)
    if _normalized_url(absolute_data_file_url) != _normalized_url(
        resolved.download_url
    ):
        raise _metadata_error("download URL does not reconcile to the catalog")

    data_file_name = meta.get("data_file_name")
    if not isinstance(data_file_name, str) or not data_file_name:
        raise _metadata_error("data file name is missing")
    release_match = _RELEASE_PATTERN.search(data_file_name)
    source_release = (
        release_match.group(0) if release_match else resolved.source_release
    )

    expected_sha1 = file_metadata.get("csvFileSHA1")
    if expected_sha1 is not None:
        if (
            not isinstance(expected_sha1, str)
            or re.fullmatch(r"[0-9a-fA-F]{40}", expected_sha1) is None
        ):
            raise _metadata_error("CSV SHA-1 is invalid")
        expected_sha1 = expected_sha1.lower()

    table_schema = meta.get("tableSchema")
    cms_table_schema_hash = None
    if isinstance(table_schema, Mapping):
        candidate = table_schema.get("hash")
        if isinstance(candidate, str):
            cms_table_schema_hash = candidate

    return CmsDataViewerMetadata(
        columns=columns,
        expected_row_count=_nonnegative_int(meta.get("total_rows"), field="total_rows"),
        expected_byte_count=_nonnegative_int(
            file_metadata.get("csvFileSize"), field="csvFileSize"
        ),
        expected_sha1=expected_sha1,
        data_file_name=data_file_name,
        source_release=source_release,
        cms_table_schema_hash=cms_table_schema_hash,
    )


def _utc_timestamp(now_value: datetime) -> str:
    if now_value.tzinfo is None or now_value.utcoffset() is None:
        raise ValueError("now() must return a timezone-aware datetime")
    return (
        now_value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def extract_cms_om_gv(
    *,
    run_id: str,
    output_root: Path,
    json_loader: JsonLoader = fetch_json,
    opener: ResponseOpener | None = None,
    sleep: Sleep = time.sleep,
    jitter: Jitter = random.random,
    now: Now = _utc_now,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> CmsExtractionResult:
    """Resolve, validate, and publish one immutable CMS full-file snapshot."""
    validate_run_id(run_id)
    catalog = json_loader(CATALOG_URL)
    resolved = resolve_current_source(catalog)
    metadata_payload = json_loader(resolved.data_viewer_url)
    metadata = parse_data_viewer_metadata(metadata_payload, resolved)

    root = output_root.resolve()
    temporary_directory = root / ".tmp" / run_id
    temporary_directory.mkdir(parents=True, exist_ok=True)
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
        if download.byte_count != metadata.expected_byte_count:
            raise CmsMetadataError(
                "downloaded byte count does not match CMS data-viewer metadata: "
                f"expected {metadata.expected_byte_count}, "
                f"received {download.byte_count}"
            )
        if (
            metadata.expected_sha1 is not None
            and download.content_sha1 != metadata.expected_sha1
        ):
            raise CmsMetadataError(
                "downloaded SHA-1 does not match CMS data-viewer metadata"
            )

        evidence = validate_raw_csv(
            staged_path,
            metadata.columns,
            expected_row_count=metadata.expected_row_count,
        )
        calculated_schema_hash = schema_sha256(metadata.columns)
        calculated_header_hash = header_sha256(evidence.header)
        blob_path = f"blobs/sha256/{download.content_sha256}.csv"
        manifest = SnapshotManifest(
            manifest_format_version=1,
            logical_source_id=SOURCE_ID,
            pipeline_run_id=run_id,
            extractor_version=EXTRACTOR_VERSION,
            contract_version=CONTRACT_VERSION,
            official_catalog_url=resolved.catalog_url,
            official_landing_url=resolved.landing_url,
            stable_dataset_id=resolved.stable_dataset_id,
            resolved_csv_url=resolved.download_url,
            retrieved_at_utc=_utc_timestamp(now()),
            source_release=metadata.source_release,
            source_modified_date=resolved.modified_date,
            http_etag=download.etag,
            http_last_modified=download.last_modified,
            content_sha256=download.content_sha256,
            byte_count=download.byte_count,
            csv_row_count=evidence.row_count,
            transport_mode="full_csv",
            page_count=1,
            record_count=evidence.row_count,
            columns=metadata.columns,
            schema_sha256=calculated_schema_hash,
            header_sha256=calculated_header_hash,
            additive_columns=evidence.additive_columns,
            blob_path=blob_path,
            content_noop=False,
        )
        publication = publish_snapshot(staged_path, root, manifest)
    except (CsvValidationError, OSError):
        raise
    finally:
        staged_path.unlink(missing_ok=True)
        with suppress(OSError):
            temporary_directory.rmdir()

    status = "published"
    if publication.manifest_noop:
        status = "manifest_noop"
    elif publication.manifest.content_noop:
        status = "content_noop"

    return CmsExtractionResult(
        status=status,
        blob_path=publication.blob_path,
        manifest_path=publication.manifest_path,
        content_sha256=download.content_sha256,
        byte_count=download.byte_count,
        row_count=evidence.row_count,
        additive_columns=evidence.additive_columns,
        retry_count=download.retry_count,
        content_noop=publication.manifest.content_noop,
        manifest_noop=publication.manifest_noop,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Resolve and extract the current official CMS Original Medicare "
            "Geographic Variation full CSV. This command performs live requests."
        )
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=Path("data/raw"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit live-source command and print concise JSON evidence."""
    arguments = _parser().parse_args(argv)
    try:
        result = extract_cms_om_gv(
            run_id=arguments.run_id,
            output_root=arguments.output_root,
        )
    except (RuntimeError, OSError, ValueError) as error:
        print(f"cms_om_gv extraction failed: {error}", file=sys.stderr)
        return 1
    summary = {
        "additive_column_count": len(result.additive_columns),
        "blob_path": str(result.blob_path),
        "byte_count": result.byte_count,
        "content_noop": result.content_noop,
        "content_sha256": result.content_sha256,
        "manifest_noop": result.manifest_noop,
        "manifest_path": str(result.manifest_path),
        "retry_count": result.retry_count,
        "row_count": result.row_count,
        "status": result.status,
    }
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
