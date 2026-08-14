"""Deterministic ArcGIS pagination for the CDC/ATSDR SVI county layer."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import shutil
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urlencode

from kidney_care_mart.contracts.cdc_svi_county_2022 import (
    CONTRACT_VERSION,
    EXPECTED_LAYER_ID,
    EXPECTED_LAYER_NAME,
    EXPECTED_OBJECT_ID_FIELD,
    REQUIRED_FIELDS,
    SOURCE_ID,
    TERRITORY_STATE_PREFIXES,
    ArcGisField,
    validate_county_rows,
    validate_layer_schema,
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

SERVICE_ITEM_ID: Final = "f2af3fd35858443293b75d5f73c7d4d3"
FEATURE_SERVICE_URL: Final = (
    "https://services3.arcgis.com/ZvidGQkLaDJxRSJ2/ArcGIS/rest/services/"
    "CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer"
)
LAYER_URL: Final = f"{FEATURE_SERVICE_URL}/{EXPECTED_LAYER_ID}"
QUERY_URL: Final = f"{LAYER_URL}/query"
SCHEMA_EVIDENCE_SHA256: Final = (
    "3bb2d1800f927dfe28f476320a67f7a000619a4bf49db22e306ce8fb7f7b6e3f"
)
EXTRACTOR_VERSION: Final = "0.1.0"
MANIFEST_FORMAT_VERSION: Final = 1
DEFAULT_PAGE_SIZE: Final = 2000
REQUESTED_FIELDS: Final = tuple(REQUIRED_FIELDS)
SOURCE_RELEASE: Final = "2022"
ACS_PERIOD: Final = "2018-2022"

Now = Callable[[], datetime]


class SviExtractionError(RuntimeError):
    """Base class for SVI extraction and publication failures."""


class SviProtocolError(SviExtractionError):
    """ArcGIS metadata or an envelope violates the expected protocol."""


class SviPaginationError(SviExtractionError):
    """Ordered pages do not reconcile to a complete county snapshot."""


class SviManifestConflictError(SviExtractionError):
    """Immutable page or run-manifest state conflicts with new evidence."""


@dataclass(frozen=True, slots=True)
class SviLayerMetadata:
    """Validated current ArcGIS layer metadata."""

    layer_id: int
    layer_name: str
    object_id_field: str
    max_record_count: int
    supports_pagination: bool
    supports_order_by: bool
    source_edit_at_utc: str | None
    fields: tuple[ArcGisField, ...]
    schema_sha256: str
    additive_fields: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SviPageManifest:
    """Immutable identity and reconciliation evidence for one exact page."""

    page_index: int
    result_offset: int
    requested_limit: int
    record_count: int
    byte_count: int
    content_sha256: str
    blob_path: str
    first_object_id: int
    last_object_id: int
    first_county_fips: str
    last_county_fips: str
    exceeded_transfer_limit: bool | None

    def identity(self) -> dict[str, int | str]:
        """Return the fields that define the ordered raw snapshot hash."""
        return {
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
            "page_index": self.page_index,
            "record_count": self.record_count,
            "result_offset": self.result_offset,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "blob_path": self.blob_path,
            "byte_count": self.byte_count,
            "content_sha256": self.content_sha256,
            "exceeded_transfer_limit": self.exceeded_transfer_limit,
            "first_county_fips": self.first_county_fips,
            "first_object_id": self.first_object_id,
            "last_county_fips": self.last_county_fips,
            "last_object_id": self.last_object_id,
            "page_index": self.page_index,
            "record_count": self.record_count,
            "requested_limit": self.requested_limit,
            "result_offset": self.result_offset,
        }


@dataclass(frozen=True, slots=True)
class SviSnapshotManifest:
    """Canonical lineage for one complete ordered SVI snapshot."""

    pipeline_run_id: str
    retrieved_at_utc: str
    source_edit_at_utc: str | None
    observed_count: int
    requested_page_size: int
    fields: tuple[ArcGisField, ...]
    schema_sha256: str
    additive_fields: tuple[str, ...]
    pages: tuple[SviPageManifest, ...]
    snapshot_sha256: str
    distinct_county_fips: int
    distinct_object_ids: int
    dc_11001_present: bool
    territory_row_count: int
    content_noop: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_format_version": MANIFEST_FORMAT_VERSION,
            "pipeline": {
                "extractor_version": EXTRACTOR_VERSION,
                "run_id": self.pipeline_run_id,
            },
            "source": {
                "feature_service_url": FEATURE_SERVICE_URL,
                "layer_id": EXPECTED_LAYER_ID,
                "layer_name": EXPECTED_LAYER_NAME,
                "layer_url": LAYER_URL,
                "logical_source_id": SOURCE_ID,
                "object_id_field": EXPECTED_OBJECT_ID_FIELD,
                "stable_service_item_id": SERVICE_ITEM_ID,
            },
            "retrieval": {
                "acs_period": ACS_PERIOD,
                "layer_last_edit_at_utc": self.source_edit_at_utc,
                "retrieved_at_utc": self.retrieved_at_utc,
                "svi_release": SOURCE_RELEASE,
            },
            "transport": {
                "count_query_result": self.observed_count,
                "filter": "1=1",
                "mode": "arcgis_rest_attributes",
                "order_by": f"{EXPECTED_OBJECT_ID_FIELD} ASC",
                "page_count": len(self.pages),
                "page_offsets": [page.result_offset for page in self.pages],
                "record_count": self.observed_count,
                "requested_page_size": self.requested_page_size,
                "return_geometry": False,
            },
            "schema": {
                "additive_fields": list(self.additive_fields),
                "contract_schema_evidence_sha256": SCHEMA_EVIDENCE_SHA256,
                "contract_version": CONTRACT_VERSION,
                "fields": [
                    {
                        "alias": field.alias,
                        "declared_type": field.declared_type,
                        "editable": field.editable,
                        "length": field.length,
                        "name": field.name,
                        "nullable": field.nullable,
                    }
                    for field in self.fields
                ],
                "requested_fields": list(REQUESTED_FIELDS),
                "schema_sha256": self.schema_sha256,
            },
            "pages": [page.to_dict() for page in self.pages],
            "content": {
                "snapshot_sha256": self.snapshot_sha256,
            },
            "reconciliation": {
                "dc_11001_present": self.dc_11001_present,
                "distinct_county_fips": self.distinct_county_fips,
                "distinct_object_ids": self.distinct_object_ids,
                "territory_row_count": self.territory_row_count,
            },
            "storage": {"content_noop": self.content_noop},
        }


@dataclass(frozen=True, slots=True)
class _StagedPage:
    manifest: SviPageManifest
    path: Path
    rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class SviExtractionResult:
    """Concise result returned by fixture and live extraction commands."""

    status: str
    manifest_path: Path
    page_paths: tuple[Path, ...]
    snapshot_sha256: str
    page_count: int
    record_count: int
    distinct_county_fips: int
    distinct_object_ids: int
    retry_count: int
    content_noop: bool
    manifest_noop: bool


@dataclass(frozen=True, slots=True)
class ReconciledSviPage:
    """One verified immutable page and its raw-token attribute rows."""

    manifest: SviPageManifest
    path: Path
    rows: tuple[Mapping[str, object], ...]


@dataclass(frozen=True, slots=True)
class ReconciledSviSnapshot:
    """A canonical manifest whose complete page set has been reverified."""

    manifest: SviSnapshotManifest
    manifest_path: Path
    pages: tuple[ReconciledSviPage, ...]


def _as_mapping(value: object, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SviProtocolError(f"{context} must be a JSON object")
    return value


def _as_sequence(value: object, *, context: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise SviProtocolError(f"{context} must be a JSON array")
    return value


def _integer(value: object, *, context: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SviProtocolError(
            f"{context} must be an integer greater than or equal to {minimum}"
        )
    return value


def _optional_boolean(value: object, *, context: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise SviProtocolError(f"{context} must be boolean when present")
    return value


def _arcgis_error(payload: Mapping[str, Any]) -> None:
    error_value = payload.get("error")
    if error_value is None:
        return
    error = _as_mapping(error_value, context="ArcGIS error")
    message = error.get("message", "unspecified ArcGIS error")
    raise SviProtocolError(f"ArcGIS error response: {message}")


def _field_from_payload(value: object, *, index: int) -> ArcGisField:
    field = _as_mapping(value, context=f"fields[{index}]")
    name = field.get("name")
    declared_type = field.get("type")
    if not isinstance(name, str) or not name:
        raise SviProtocolError(f"fields[{index}].name must be nonblank text")
    if not isinstance(declared_type, str) or not declared_type:
        raise SviProtocolError(f"fields[{index}].type must be nonblank text")

    alias = field.get("alias")
    if alias is not None and not isinstance(alias, str):
        raise SviProtocolError(f"fields[{index}].alias must be text or null")
    length = field.get("length")
    if length is not None and (type(length) is not int or length < 1):
        raise SviProtocolError(f"fields[{index}].length must be a positive integer")
    nullable = field.get("nullable")
    if nullable is not None and type(nullable) is not bool:
        raise SviProtocolError(f"fields[{index}].nullable must be boolean or null")
    editable = field.get("editable")
    if editable is not None and type(editable) is not bool:
        raise SviProtocolError(f"fields[{index}].editable must be boolean or null")
    return ArcGisField(
        name=name,
        declared_type=declared_type,
        alias=alias,
        length=length,
        nullable=nullable,
        editable=editable,
    )


def _epoch_milliseconds_to_utc(value: object) -> str | None:
    if value is None:
        return None
    milliseconds = _integer(value, context="editingInfo.lastEditDate", minimum=1)
    try:
        timestamp = datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise SviProtocolError("editingInfo.lastEditDate is out of range") from error
    return timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def _field_schema_sha256(fields: Sequence[ArcGisField]) -> str:
    return canonical_json_sha256(
        [{"declared_type": field.declared_type, "name": field.name} for field in fields]
    )


def parse_layer_metadata(payload: Mapping[str, Any]) -> SviLayerMetadata:
    """Parse and contract-check current ArcGIS layer metadata."""
    _arcgis_error(payload)
    raw_fields = _as_sequence(payload.get("fields"), context="fields")
    fields = tuple(
        _field_from_payload(value, index=index)
        for index, value in enumerate(raw_fields)
    )
    result = validate_layer_schema(
        layer_id=payload.get("id"),
        layer_name=payload.get("name"),
        object_id_field=payload.get("objectIdField"),
        fields=fields,
    )
    if not result.is_valid:
        raise SviProtocolError(
            "SVI layer contract failed: "
            + "; ".join(issue.message for issue in result.issues)
        )

    capabilities = _as_mapping(
        payload.get("advancedQueryCapabilities"),
        context="advancedQueryCapabilities",
    )
    supports_pagination = capabilities.get("supportsPagination")
    supports_order_by = capabilities.get("supportsOrderBy")
    if supports_pagination is not True:
        raise SviProtocolError("SVI layer must support pagination")
    if supports_order_by is not True:
        raise SviProtocolError("SVI layer must support deterministic ordering")
    max_record_count = _integer(
        payload.get("maxRecordCount"),
        context="maxRecordCount",
        minimum=1,
    )
    editing = payload.get("editingInfo")
    source_edit_at_utc = None
    if editing is not None:
        source_edit_at_utc = _epoch_milliseconds_to_utc(
            _as_mapping(editing, context="editingInfo").get("lastEditDate")
        )

    return SviLayerMetadata(
        layer_id=EXPECTED_LAYER_ID,
        layer_name=EXPECTED_LAYER_NAME,
        object_id_field=EXPECTED_OBJECT_ID_FIELD,
        max_record_count=max_record_count,
        supports_pagination=True,
        supports_order_by=True,
        source_edit_at_utc=source_edit_at_utc,
        fields=fields,
        schema_sha256=_field_schema_sha256(fields),
        additive_fields=result.additive_fields,
    )


def parse_count_response(payload: Mapping[str, Any]) -> int:
    """Return one validated ArcGIS count-only result."""
    _arcgis_error(payload)
    if "count" not in payload:
        raise SviProtocolError("ArcGIS count response is missing count")
    return _integer(payload["count"], context="count", minimum=0)


def _metadata_url() -> str:
    return f"{LAYER_URL}?{urlencode([('f', 'json')])}"


def _count_url() -> str:
    return f"{QUERY_URL}?{urlencode([('where', '1=1'), ('returnCountOnly', 'true'), ('f', 'json')])}"


def _page_url(*, offset: int, page_size: int) -> str:
    parameters = [
        ("where", "1=1"),
        ("outFields", ",".join(REQUESTED_FIELDS)),
        ("returnGeometry", "false"),
        ("orderByFields", f"{EXPECTED_OBJECT_ID_FIELD} ASC"),
        ("resultOffset", str(offset)),
        ("resultRecordCount", str(page_size)),
        ("f", "json"),
    ]
    return f"{QUERY_URL}?{urlencode(parameters)}"


def _read_page_payload(body: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(body, parse_int=str, parse_float=str)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SviProtocolError("ArcGIS page is not valid UTF-8 JSON") from error
    parsed = _as_mapping(payload, context="ArcGIS page")
    _arcgis_error(parsed)
    return parsed


def _parse_page(
    *,
    body: bytes,
    path: Path,
    page_index: int,
    result_offset: int,
    requested_limit: int,
    expected_count: int,
) -> _StagedPage:
    payload = _read_page_payload(body)
    features = _as_sequence(payload.get("features"), context="features")
    if len(features) != expected_count:
        raise SviPaginationError(
            f"page at offset {result_offset} expected {expected_count} records, "
            f"received {len(features)}"
        )
    if len(features) > requested_limit:
        raise SviPaginationError(
            f"page at offset {result_offset} exceeds requested page limit"
        )

    rows: list[Mapping[str, object]] = []
    requested = set(REQUESTED_FIELDS)
    for feature_index, raw_feature in enumerate(features):
        feature = _as_mapping(
            raw_feature,
            context=f"features[{feature_index}]",
        )
        if "geometry" in feature:
            raise SviPaginationError(
                f"features[{feature_index}] unexpectedly contains geometry"
            )
        attributes = _as_mapping(
            feature.get("attributes"),
            context=f"features[{feature_index}].attributes",
        )
        missing = sorted(requested.difference(attributes))
        if missing:
            raise SviPaginationError(
                "feature is missing required attributes: " + ", ".join(missing)
            )
        unexpected = sorted(set(attributes).difference(requested))
        if unexpected:
            raise SviPaginationError(
                "feature contains attributes outside the explicit projection: "
                + ", ".join(unexpected)
            )
        rows.append({field: attributes[field] for field in REQUESTED_FIELDS})

    if not rows:
        raise SviPaginationError(
            f"page at offset {result_offset} cannot be empty before completion"
        )
    object_ids: list[int] = []
    county_fips: list[str] = []
    for row in rows:
        try:
            object_ids.append(int(str(row[EXPECTED_OBJECT_ID_FIELD])))
        except (TypeError, ValueError) as error:
            raise SviPaginationError("page contains invalid GRASP_ID") from error
        county_value = row.get("STCNTY")
        if not isinstance(county_value, str):
            raise SviPaginationError("page contains non-text county FIPS")
        county_fips.append(county_value)

    content_sha256 = hashlib.sha256(body).hexdigest()
    page_manifest = SviPageManifest(
        page_index=page_index,
        result_offset=result_offset,
        requested_limit=requested_limit,
        record_count=len(rows),
        byte_count=len(body),
        content_sha256=content_sha256,
        blob_path=f"blobs/sha256/{content_sha256}.json",
        first_object_id=object_ids[0],
        last_object_id=object_ids[-1],
        first_county_fips=county_fips[0],
        last_county_fips=county_fips[-1],
        exceeded_transfer_limit=_optional_boolean(
            payload.get("exceededTransferLimit"),
            context="exceededTransferLimit",
        ),
    )
    return _StagedPage(manifest=page_manifest, path=path, rows=tuple(rows))


def _validate_complete_pages(
    pages: Sequence[_StagedPage],
    *,
    observed_count: int,
) -> tuple[int, int, bool, int]:
    rows = tuple(row for page in pages for row in page.rows)
    if len(rows) != observed_count:
        raise SviPaginationError(
            "summed page records do not match the count query: "
            f"{len(rows)} != {observed_count}"
        )

    grain_result = validate_county_rows(rows)
    if not grain_result.is_valid:
        raise SviPaginationError(
            "SVI county pagination grain failed: "
            + "; ".join(issue.message for issue in grain_result.issues)
        )

    object_ids = [int(str(row[EXPECTED_OBJECT_ID_FIELD])) for row in rows]
    if any(current <= previous for previous, current in pairwise(object_ids)):
        raise SviPaginationError(
            "GRASP_ID values must be globally unique and strictly increasing"
        )
    county_fips = [str(row["STCNTY"]) for row in rows]
    distinct_object_ids = len(set(object_ids))
    distinct_county_fips = len(set(county_fips))
    if distinct_object_ids != observed_count:
        raise SviPaginationError("GRASP_ID values are not globally distinct")
    if distinct_county_fips != observed_count:
        raise SviPaginationError("county FIPS values are not globally distinct")

    dc_present = "11001" in county_fips
    if not dc_present:
        raise SviPaginationError("complete U.S. county snapshot is missing DC 11001")
    territory_count = sum(fips[:2] in TERRITORY_STATE_PREFIXES for fips in county_fips)
    if territory_count:
        raise SviPaginationError(
            "complete U.S. county snapshot contains out-of-scope territories"
        )
    return distinct_county_fips, distinct_object_ids, dc_present, territory_count


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


def _resolve_blob(root: Path, relative_path: str) -> Path:
    relative = PurePosixPath(relative_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise SviManifestConflictError("manifest page path escapes the raw root")
    resolved = root.joinpath(*relative.parts).resolve()
    if not resolved.is_relative_to(root):
        raise SviManifestConflictError("manifest page path escapes the raw root")
    return resolved


def _verify_page_blob(path: Path, page: SviPageManifest) -> None:
    try:
        actual_hash, actual_bytes = _hash_file(path)
    except OSError as error:
        raise SviManifestConflictError(
            f"existing page blob integrity check failed: {path}"
        ) from error
    if actual_hash != page.content_sha256 or actual_bytes != page.byte_count:
        raise SviManifestConflictError(
            f"existing page blob failed integrity checks: {path}"
        )


def _write_atomic_new(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    if temporary.exists():
        raise SviManifestConflictError(
            f"manifest staging path already exists: {temporary}"
        )
    try:
        with temporary.open("xb") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise SviManifestConflictError(
                f"run manifest appeared concurrently: {path}"
            ) from error
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_from_bytes(content: bytes) -> Mapping[str, Any]:
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SviManifestConflictError("existing manifest is invalid JSON") from error
    parsed = _as_mapping(payload, context="existing manifest")
    if canonical_json_bytes(parsed) != content:
        raise SviManifestConflictError("existing manifest is not canonical JSON")
    return parsed


def _manifest_mapping(value: object, *, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SviManifestConflictError(f"manifest field {field} must be an object")
    return value


def _manifest_sequence(value: object, *, field: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise SviManifestConflictError(f"manifest field {field} must be an array")
    return value


def _manifest_string(
    value: object,
    *,
    field: str,
    nullable: bool = False,
) -> str | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise SviManifestConflictError(f"manifest field {field} must be text")
    return value


def _manifest_integer(value: object, *, field: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise SviManifestConflictError(
            f"manifest field {field} must be an integer >= {minimum}"
        )
    return value


def _manifest_boolean(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        raise SviManifestConflictError(f"manifest field {field} must be boolean")
    return value


def _manifest_optional_boolean(value: object, *, field: str) -> bool | None:
    if value is None:
        return None
    return _manifest_boolean(value, field=field)


def _manifest_hash(value: object, *, field: str) -> str:
    text = _manifest_string(value, field=field)
    if len(text) != 64 or any(
        character not in "0123456789abcdef" for character in text
    ):
        raise SviManifestConflictError(
            f"manifest field {field} must be a lowercase SHA-256"
        )
    return text


def _manifest_field(value: object, *, index: int) -> ArcGisField:
    field = _manifest_mapping(value, field=f"schema.fields[{index}]")
    length_value = field.get("length")
    length = None
    if length_value is not None:
        length = _manifest_integer(
            length_value,
            field=f"schema.fields[{index}].length",
            minimum=1,
        )
    nullable_value = field.get("nullable")
    nullable = None
    if nullable_value is not None:
        nullable = _manifest_boolean(
            nullable_value,
            field=f"schema.fields[{index}].nullable",
        )
    editable_value = field.get("editable")
    editable = None
    if editable_value is not None:
        editable = _manifest_boolean(
            editable_value,
            field=f"schema.fields[{index}].editable",
        )
    return ArcGisField(
        name=_manifest_string(field.get("name"), field=f"schema.fields[{index}].name"),
        declared_type=_manifest_string(
            field.get("declared_type"),
            field=f"schema.fields[{index}].declared_type",
        ),
        alias=_manifest_string(
            field.get("alias"),
            field=f"schema.fields[{index}].alias",
            nullable=True,
        ),
        length=length,
        nullable=nullable,
        editable=editable,
    )


def _manifest_page(value: object, *, index: int) -> SviPageManifest:
    page = _manifest_mapping(value, field=f"pages[{index}]")
    return SviPageManifest(
        page_index=_manifest_integer(
            page.get("page_index"), field=f"pages[{index}].page_index"
        ),
        result_offset=_manifest_integer(
            page.get("result_offset"), field=f"pages[{index}].result_offset"
        ),
        requested_limit=_manifest_integer(
            page.get("requested_limit"),
            field=f"pages[{index}].requested_limit",
            minimum=1,
        ),
        record_count=_manifest_integer(
            page.get("record_count"),
            field=f"pages[{index}].record_count",
            minimum=1,
        ),
        byte_count=_manifest_integer(
            page.get("byte_count"),
            field=f"pages[{index}].byte_count",
            minimum=1,
        ),
        content_sha256=_manifest_hash(
            page.get("content_sha256"),
            field=f"pages[{index}].content_sha256",
        ),
        blob_path=_manifest_string(
            page.get("blob_path"), field=f"pages[{index}].blob_path"
        ),
        first_object_id=_manifest_integer(
            page.get("first_object_id"),
            field=f"pages[{index}].first_object_id",
            minimum=1,
        ),
        last_object_id=_manifest_integer(
            page.get("last_object_id"),
            field=f"pages[{index}].last_object_id",
            minimum=1,
        ),
        first_county_fips=_manifest_string(
            page.get("first_county_fips"),
            field=f"pages[{index}].first_county_fips",
        ),
        last_county_fips=_manifest_string(
            page.get("last_county_fips"),
            field=f"pages[{index}].last_county_fips",
        ),
        exceeded_transfer_limit=_manifest_optional_boolean(
            page.get("exceeded_transfer_limit"),
            field=f"pages[{index}].exceeded_transfer_limit",
        ),
    )


def snapshot_manifest_from_payload(
    payload: Mapping[str, Any],
) -> SviSnapshotManifest:
    """Parse the canonical public manifest shape without trusting its values."""
    try:
        version = _manifest_integer(
            payload.get("manifest_format_version"),
            field="manifest_format_version",
            minimum=1,
        )
        if version != MANIFEST_FORMAT_VERSION:
            raise SviManifestConflictError(
                f"unsupported manifest format version: {version}"
            )
        pipeline = _manifest_mapping(payload.get("pipeline"), field="pipeline")
        source = _manifest_mapping(payload.get("source"), field="source")
        retrieval = _manifest_mapping(payload.get("retrieval"), field="retrieval")
        transport = _manifest_mapping(payload.get("transport"), field="transport")
        schema = _manifest_mapping(payload.get("schema"), field="schema")
        content = _manifest_mapping(payload.get("content"), field="content")
        reconciliation = _manifest_mapping(
            payload.get("reconciliation"), field="reconciliation"
        )
        storage = _manifest_mapping(payload.get("storage"), field="storage")

        expected_source = {
            "feature_service_url": FEATURE_SERVICE_URL,
            "layer_id": EXPECTED_LAYER_ID,
            "layer_name": EXPECTED_LAYER_NAME,
            "layer_url": LAYER_URL,
            "logical_source_id": SOURCE_ID,
            "object_id_field": EXPECTED_OBJECT_ID_FIELD,
            "stable_service_item_id": SERVICE_ITEM_ID,
        }
        if source != expected_source:
            raise SviManifestConflictError(
                "manifest source identity does not match the supported SVI layer"
            )
        if retrieval.get("svi_release") != SOURCE_RELEASE:
            raise SviManifestConflictError("manifest SVI release is unsupported")
        if retrieval.get("acs_period") != ACS_PERIOD:
            raise SviManifestConflictError("manifest ACS period is unsupported")
        if schema.get("contract_version") != CONTRACT_VERSION:
            raise SviManifestConflictError("manifest contract version is unsupported")
        if schema.get("contract_schema_evidence_sha256") != SCHEMA_EVIDENCE_SHA256:
            raise SviManifestConflictError(
                "manifest contract schema evidence is unsupported"
            )
        if schema.get("requested_fields") != list(REQUESTED_FIELDS):
            raise SviManifestConflictError(
                "manifest requested fields do not match the SVI contract"
            )
        if (
            transport.get("mode") != "arcgis_rest_attributes"
            or transport.get("filter") != "1=1"
            or transport.get("order_by") != f"{EXPECTED_OBJECT_ID_FIELD} ASC"
            or transport.get("return_geometry") is not False
        ):
            raise SviManifestConflictError(
                "manifest transport shape does not match the SVI query contract"
            )

        raw_fields = _manifest_sequence(schema.get("fields"), field="schema.fields")
        fields = tuple(
            _manifest_field(value, index=index)
            for index, value in enumerate(raw_fields)
        )
        contract_result = validate_layer_schema(
            layer_id=source.get("layer_id"),
            layer_name=source.get("layer_name"),
            object_id_field=source.get("object_id_field"),
            fields=fields,
        )
        if not contract_result.is_valid:
            raise SviManifestConflictError(
                "manifest schema violates the SVI contract: "
                + "; ".join(issue.message for issue in contract_result.issues)
            )
        schema_hash = _manifest_hash(
            schema.get("schema_sha256"), field="schema.schema_sha256"
        )
        if schema_hash != _field_schema_sha256(fields):
            raise SviManifestConflictError("manifest schema hash does not reconcile")
        additives = tuple(
            _manifest_string(
                value,
                field=f"schema.additive_fields[{index}]",
            )
            for index, value in enumerate(
                _manifest_sequence(
                    schema.get("additive_fields"), field="schema.additive_fields"
                )
            )
        )
        if additives != contract_result.additive_fields:
            raise SviManifestConflictError(
                "manifest additive fields do not reconcile to metadata"
            )

        raw_pages = _manifest_sequence(payload.get("pages"), field="pages")
        pages = tuple(
            _manifest_page(value, index=index) for index, value in enumerate(raw_pages)
        )
        observed_count = _manifest_integer(
            transport.get("count_query_result"),
            field="transport.count_query_result",
        )
        if transport.get("record_count") != observed_count:
            raise SviManifestConflictError(
                "manifest record count does not match its count query"
            )
        page_size = _manifest_integer(
            transport.get("requested_page_size"),
            field="transport.requested_page_size",
            minimum=1,
        )
        if page_size > DEFAULT_PAGE_SIZE:
            raise SviManifestConflictError(
                "manifest page size exceeds the supported SVI maximum"
            )
        expected_offsets = list(range(0, observed_count, page_size))
        if transport.get("page_offsets") != expected_offsets:
            raise SviManifestConflictError("manifest page offsets do not reconcile")
        if transport.get("page_count") != len(pages):
            raise SviManifestConflictError("manifest page count does not reconcile")
        if [page.result_offset for page in pages] != expected_offsets:
            raise SviManifestConflictError("manifest pages are not in offset order")
        for index, page in enumerate(pages):
            expected_records = min(page_size, observed_count - page.result_offset)
            if page.page_index != index:
                raise SviManifestConflictError(
                    "manifest page indexes are not contiguous"
                )
            if page.requested_limit != page_size:
                raise SviManifestConflictError(
                    "manifest page limit does not match transport"
                )
            if page.record_count != expected_records:
                raise SviManifestConflictError(
                    "manifest page row count does not cover the requested offset"
                )
            expected_path = f"blobs/sha256/{page.content_sha256}.json"
            if page.blob_path != expected_path:
                raise SviManifestConflictError(
                    "manifest page path escapes its content-addressed identity"
                )

        manifest = SviSnapshotManifest(
            pipeline_run_id=_manifest_string(
                pipeline.get("run_id"), field="pipeline.run_id"
            ),
            retrieved_at_utc=_manifest_string(
                retrieval.get("retrieved_at_utc"),
                field="retrieval.retrieved_at_utc",
            ),
            source_edit_at_utc=_manifest_string(
                retrieval.get("layer_last_edit_at_utc"),
                field="retrieval.layer_last_edit_at_utc",
                nullable=True,
            ),
            observed_count=observed_count,
            requested_page_size=page_size,
            fields=fields,
            schema_sha256=schema_hash,
            additive_fields=additives,
            pages=pages,
            snapshot_sha256=_manifest_hash(
                content.get("snapshot_sha256"),
                field="content.snapshot_sha256",
            ),
            distinct_county_fips=_manifest_integer(
                reconciliation.get("distinct_county_fips"),
                field="reconciliation.distinct_county_fips",
            ),
            distinct_object_ids=_manifest_integer(
                reconciliation.get("distinct_object_ids"),
                field="reconciliation.distinct_object_ids",
            ),
            dc_11001_present=_manifest_boolean(
                reconciliation.get("dc_11001_present"),
                field="reconciliation.dc_11001_present",
            ),
            territory_row_count=_manifest_integer(
                reconciliation.get("territory_row_count"),
                field="reconciliation.territory_row_count",
            ),
            content_noop=_manifest_boolean(
                storage.get("content_noop"), field="storage.content_noop"
            ),
        )
    except KeyError as error:
        raise SviManifestConflictError(
            f"manifest is missing required field: {error.args[0]}"
        ) from error

    validate_run_id(manifest.pipeline_run_id)
    if payload != manifest.to_dict():
        raise SviManifestConflictError(
            "manifest shape contains unsupported or inconsistent fields"
        )
    return manifest


def load_and_reconcile_svi_snapshot(
    manifest_path: Path,
    raw_root: Path,
) -> ReconciledSviSnapshot:
    """Load a canonical manifest and independently verify all referenced pages."""
    root = raw_root.resolve()
    resolved_manifest = manifest_path.resolve()
    manifests_root = (root / "manifests" / SOURCE_ID).resolve()
    if not resolved_manifest.is_relative_to(manifests_root):
        raise SviManifestConflictError(
            "manifest path must be beneath the configured SVI manifest root"
        )
    try:
        manifest_bytes = resolved_manifest.read_bytes()
    except OSError as error:
        raise SviManifestConflictError(
            f"cannot read SVI manifest: {resolved_manifest}"
        ) from error
    payload = _manifest_from_bytes(manifest_bytes)
    manifest = snapshot_manifest_from_payload(payload)

    reconciled_pages: list[ReconciledSviPage] = []
    staged_pages: list[_StagedPage] = []
    for page in manifest.pages:
        page_path = _resolve_blob(root, page.blob_path)
        _verify_page_blob(page_path, page)
        try:
            body = page_path.read_bytes()
        except OSError as error:
            raise SviManifestConflictError(
                f"cannot read SVI page blob: {page_path}"
            ) from error
        parsed = _parse_page(
            body=body,
            path=page_path,
            page_index=page.page_index,
            result_offset=page.result_offset,
            requested_limit=page.requested_limit,
            expected_count=page.record_count,
        )
        if parsed.manifest != page:
            raise SviManifestConflictError(
                "manifest page evidence does not reconcile to exact page bytes"
            )
        staged_pages.append(parsed)
        reconciled_pages.append(
            ReconciledSviPage(
                manifest=page,
                path=page_path,
                rows=parsed.rows,
            )
        )

    (
        distinct_county_fips,
        distinct_object_ids,
        dc_present,
        territory_count,
    ) = _validate_complete_pages(
        staged_pages,
        observed_count=manifest.observed_count,
    )
    expected_snapshot_hash = canonical_json_sha256(
        [page.identity() for page in manifest.pages]
    )
    if manifest.snapshot_sha256 != expected_snapshot_hash:
        raise SviManifestConflictError("manifest snapshot hash does not reconcile")
    if (
        manifest.distinct_county_fips != distinct_county_fips
        or manifest.distinct_object_ids != distinct_object_ids
        or manifest.dc_11001_present != dc_present
        or manifest.territory_row_count != territory_count
    ):
        raise SviManifestConflictError(
            "manifest reconciliation summary does not match its pages"
        )
    return ReconciledSviSnapshot(
        manifest=manifest,
        manifest_path=resolved_manifest,
        pages=tuple(reconciled_pages),
    )


def _publish_snapshot(
    *,
    root: Path,
    manifest: SviSnapshotManifest,
    staged_pages: Sequence[_StagedPage],
) -> tuple[SviSnapshotManifest, Path, tuple[Path, ...], bool]:
    manifest_path = (
        root / "manifests" / SOURCE_ID / f"{manifest.pipeline_run_id}.json"
    ).resolve()
    if not manifest_path.is_relative_to(root):
        raise SviManifestConflictError("run manifest path escapes the raw root")

    if manifest_path.exists():
        existing_bytes = manifest_path.read_bytes()
        existing = _manifest_from_bytes(existing_bytes)
        storage = _as_mapping(existing.get("storage"), context="storage")
        existing_noop = storage.get("content_noop")
        if type(existing_noop) is not bool:
            raise SviManifestConflictError(
                "existing manifest content_noop must be boolean"
            )
        candidate = replace(manifest, content_noop=existing_noop)
        if canonical_json_bytes(candidate.to_dict()) != existing_bytes:
            raise SviManifestConflictError(
                f"run manifest already exists with different lineage: {manifest_path}"
            )
        page_paths = tuple(
            _resolve_blob(root, page.blob_path) for page in candidate.pages
        )
        for page, page_path in zip(candidate.pages, page_paths, strict=True):
            _verify_page_blob(page_path, page)
        return candidate, manifest_path, page_paths, True

    page_paths = tuple(
        _resolve_blob(root, page.manifest.blob_path) for page in staged_pages
    )
    content_noop = all(path.exists() for path in page_paths)
    final_manifest = replace(manifest, content_noop=content_noop)

    for staged_page, final_path in zip(staged_pages, page_paths, strict=True):
        if final_path.exists():
            _verify_page_blob(final_path, staged_page.manifest)
            continue
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(staged_page.path, final_path)
        except FileExistsError:
            _verify_page_blob(final_path, staged_page.manifest)
        _verify_page_blob(final_path, staged_page.manifest)

    _write_atomic_new(manifest_path, canonical_json_bytes(final_manifest.to_dict()))
    return final_manifest, manifest_path, page_paths, False


def _load_json_with_http(
    url: str,
    *,
    opener: ResponseOpener | None,
    sleep: Sleep,
    jitter: Jitter,
    retry_policy: RetryPolicy,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "sleep": sleep,
        "jitter": jitter,
        "retry_policy": retry_policy,
    }
    if opener is not None:
        kwargs["opener"] = opener
    return fetch_json(url, **kwargs)


def extract_cdc_svi_county_2022(
    *,
    run_id: str,
    output_root: Path,
    opener: ResponseOpener | None = None,
    sleep: Sleep = time.sleep,
    jitter: Jitter = random.random,
    now: Now = _utc_now,
    page_size: int = DEFAULT_PAGE_SIZE,
    retry_policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> SviExtractionResult:
    """Extract, reconcile, and publish one complete SVI county snapshot."""
    validate_run_id(run_id)
    if type(page_size) is not int or page_size < 1:
        raise ValueError("page_size must be a positive integer")

    metadata = parse_layer_metadata(
        _load_json_with_http(
            _metadata_url(),
            opener=opener,
            sleep=sleep,
            jitter=jitter,
            retry_policy=retry_policy,
        )
    )
    if page_size > metadata.max_record_count:
        raise SviProtocolError(
            "requested page size exceeds the layer maximum: "
            f"{page_size} > {metadata.max_record_count}"
        )
    observed_count = parse_count_response(
        _load_json_with_http(
            _count_url(),
            opener=opener,
            sleep=sleep,
            jitter=jitter,
            retry_policy=retry_policy,
        )
    )

    root = output_root.resolve()
    temporary_directory = root / ".tmp" / run_id
    temporary_directory.mkdir(parents=True, exist_ok=False)
    staged_pages: list[_StagedPage] = []
    retry_count = 0
    try:
        offsets = range(0, observed_count, page_size)
        for page_index, offset in enumerate(offsets):
            expected_count = min(page_size, observed_count - offset)
            staged_path = temporary_directory / f"page-{offset:09d}.json.partial"
            download_kwargs: dict[str, Any] = {
                "accept": "application/json",
                "sleep": sleep,
                "jitter": jitter,
                "retry_policy": retry_policy,
            }
            if opener is not None:
                download_kwargs["opener"] = opener
            download = stream_download(
                _page_url(offset=offset, page_size=page_size),
                staged_path,
                **download_kwargs,
            )
            retry_count += download.retry_count
            staged_pages.append(
                _parse_page(
                    body=staged_path.read_bytes(),
                    path=staged_path,
                    page_index=page_index,
                    result_offset=offset,
                    requested_limit=page_size,
                    expected_count=expected_count,
                )
            )

        (
            distinct_county_fips,
            distinct_object_ids,
            dc_present,
            territory_count,
        ) = _validate_complete_pages(staged_pages, observed_count=observed_count)
        page_manifests = tuple(page.manifest for page in staged_pages)
        snapshot_sha256 = canonical_json_sha256(
            [page.identity() for page in page_manifests]
        )
        manifest = SviSnapshotManifest(
            pipeline_run_id=run_id,
            retrieved_at_utc=_utc_timestamp(now()),
            source_edit_at_utc=metadata.source_edit_at_utc,
            observed_count=observed_count,
            requested_page_size=page_size,
            fields=metadata.fields,
            schema_sha256=metadata.schema_sha256,
            additive_fields=metadata.additive_fields,
            pages=page_manifests,
            snapshot_sha256=snapshot_sha256,
            distinct_county_fips=distinct_county_fips,
            distinct_object_ids=distinct_object_ids,
            dc_11001_present=dc_present,
            territory_row_count=territory_count,
        )
        final_manifest, manifest_path, page_paths, manifest_noop = _publish_snapshot(
            root=root,
            manifest=manifest,
            staged_pages=staged_pages,
        )
    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)
        with suppress(OSError):
            temporary_directory.parent.rmdir()

    status = "published"
    if manifest_noop:
        status = "manifest_noop"
    elif final_manifest.content_noop:
        status = "content_noop"
    return SviExtractionResult(
        status=status,
        manifest_path=manifest_path,
        page_paths=page_paths,
        snapshot_sha256=final_manifest.snapshot_sha256,
        page_count=len(final_manifest.pages),
        record_count=final_manifest.observed_count,
        distinct_county_fips=final_manifest.distinct_county_fips,
        distinct_object_ids=final_manifest.distinct_object_ids,
        retry_count=retry_count,
        content_noop=final_manifest.content_noop,
        manifest_noop=manifest_noop,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract the public CDC/ATSDR SVI 2022 U.S. county layer."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicit live SVI extraction command."""
    arguments = _parser().parse_args(argv)
    result = extract_cdc_svi_county_2022(
        run_id=arguments.run_id,
        output_root=arguments.output_root,
        page_size=arguments.page_size,
    )
    print(
        json.dumps(
            {
                "content_noop": result.content_noop,
                "distinct_county_fips": result.distinct_county_fips,
                "distinct_object_ids": result.distinct_object_ids,
                "manifest_noop": result.manifest_noop,
                "manifest_path": str(result.manifest_path),
                "page_count": result.page_count,
                "page_paths": [str(path) for path in result.page_paths],
                "record_count": result.record_count,
                "retry_count": result.retry_count,
                "snapshot_sha256": result.snapshot_sha256,
                "status": result.status,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
