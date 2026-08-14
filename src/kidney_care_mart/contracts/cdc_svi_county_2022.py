"""Raw-boundary contract for the CDC/ATSDR SVI 2022 U.S. county layer.

This module validates the official ArcGIS layer identity, required field labels,
declared type families, and county grain. It deliberately does not normalize the
SVI ``-999`` sentinel, bound rank values, download pages, or join another source.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

SOURCE_ID: Final = "cdc_svi_county_2022"
CONTRACT_VERSION: Final = "cdc_svi_county_2022.raw.v1"
EXPECTED_LAYER_ID: Final = 1
EXPECTED_LAYER_NAME: Final = "SVI2022 US county"
EXPECTED_OBJECT_ID_FIELD: Final = "GRASP_ID"

REQUIRED_FIELDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "ST": "string",
        "STATE": "string",
        "ST_ABBR": "string",
        "STCNTY": "string",
        "COUNTY": "string",
        "RPL_THEMES": "numeric",
        "RPL_THEME1": "numeric",
        "RPL_THEME2": "numeric",
        "RPL_THEME3": "numeric",
        "RPL_THEME4": "numeric",
        "EP_POV150": "numeric",
        "EP_UNINSUR": "numeric",
        "EP_AGE65": "numeric",
        "EP_DISABL": "numeric",
        "EP_LIMENG": "numeric",
        "EP_NOVEH": "numeric",
        "GRASP_ID": "oid",
    }
)

GRAIN_KEYS: Final = ("ST", "STATE", "ST_ABBR", "STCNTY", "COUNTY", "GRASP_ID")
TERRITORY_STATE_PREFIXES: Final = frozenset({"60", "66", "69", "72", "78"})

_COMPATIBLE_DECLARED_TYPES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "string": frozenset({"esriFieldTypeString"}),
        "numeric": frozenset(
            {
                "esriFieldTypeDouble",
                "esriFieldTypeInteger",
                "esriFieldTypeSingle",
                "esriFieldTypeSmallInteger",
            }
        ),
        "oid": frozenset({"esriFieldTypeOID"}),
    }
)
_STATE_FIPS_PATTERN: Final = re.compile(r"^[0-9]{2}$", flags=re.ASCII)
_COUNTY_FIPS_PATTERN: Final = re.compile(r"^[0-9]{5}$", flags=re.ASCII)
_POSITIVE_INTEGER_PATTERN: Final = re.compile(r"^[1-9][0-9]*$", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class ArcGisField:
    """One ArcGIS field label and its declared transport metadata."""

    name: str
    declared_type: str
    alias: str | None = None
    length: int | None = None
    nullable: bool | None = None
    editable: bool | None = None


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One deterministic contract issue suitable for audit logging."""

    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Structured source-contract output."""

    issues: tuple[ValidationIssue, ...] = ()
    additive_fields: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether no blocking contract issue was found."""
        return not self.issues


def validate_layer_schema(
    *,
    layer_id: object,
    layer_name: object,
    object_id_field: object,
    fields: Iterable[ArcGisField],
) -> ValidationResult:
    """Validate the exact SVI county layer and its required ArcGIS fields."""
    observed = tuple(fields)
    name_counts = Counter(field.name for field in observed)
    first_field_by_name: dict[str, ArcGisField] = {}
    for field in observed:
        first_field_by_name.setdefault(field.name, field)

    issues: list[ValidationIssue] = []
    if layer_id != EXPECTED_LAYER_ID:
        issues.append(
            ValidationIssue(
                code="unexpected_layer_id",
                field="layer_id",
                message=(
                    f"Unexpected ArcGIS layer ID {layer_id!r}; "
                    f"expected {EXPECTED_LAYER_ID}"
                ),
            )
        )
    if layer_name != EXPECTED_LAYER_NAME:
        issues.append(
            ValidationIssue(
                code="unexpected_layer_name",
                field="layer_name",
                message=(
                    f"Unexpected ArcGIS layer name {layer_name!r}; "
                    f"expected {EXPECTED_LAYER_NAME!r}"
                ),
            )
        )
    if object_id_field != EXPECTED_OBJECT_ID_FIELD:
        issues.append(
            ValidationIssue(
                code="unexpected_object_id_field",
                field="object_id_field",
                message=(
                    f"Unexpected ArcGIS object-ID field {object_id_field!r}; "
                    f"expected {EXPECTED_OBJECT_ID_FIELD!r}"
                ),
            )
        )

    for field_name, expected_family in REQUIRED_FIELDS.items():
        count = name_counts[field_name]
        if count == 0:
            issues.append(
                ValidationIssue(
                    code="missing_required_field",
                    field=field_name,
                    message=f"Required ArcGIS field is missing: {field_name}",
                )
            )
            continue
        if count > 1:
            issues.append(
                ValidationIssue(
                    code="duplicate_required_field",
                    field=field_name,
                    message=(
                        f"Required ArcGIS field appears more than once: {field_name}"
                    ),
                )
            )
            continue

        declared_type = first_field_by_name[field_name].declared_type.strip()
        if declared_type not in _COMPATIBLE_DECLARED_TYPES[expected_family]:
            issues.append(
                ValidationIssue(
                    code="incompatible_required_type",
                    field=field_name,
                    message=(
                        f"Required ArcGIS field {field_name} has incompatible "
                        f"declared type {declared_type}; expected {expected_family}"
                    ),
                )
            )

    additive_fields = tuple(sorted(set(name_counts).difference(REQUIRED_FIELDS)))
    return ValidationResult(
        issues=tuple(issues),
        additive_fields=additive_fields,
    )


def _validate_fips(
    row: Mapping[str, object],
    field: str,
    pattern: re.Pattern[str],
    width: int,
) -> tuple[str | None, ValidationIssue | None]:
    value = row.get(field)
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        return None, ValidationIssue(
            code="invalid_fips",
            field=field,
            message=f"{field} must be {width}-character ASCII-digit text: {value!r}",
        )
    return value, None


def _object_id_is_valid(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value > 0
    return (
        isinstance(value, str)
        and _POSITIVE_INTEGER_PATTERN.fullmatch(value) is not None
    )


def validate_grain_keys(row: Mapping[str, object]) -> ValidationResult:
    """Validate one source county grain without coercing its FIPS values."""
    issues: list[ValidationIssue] = []
    missing_keys = [key for key in GRAIN_KEYS if key not in row]
    issues.extend(
        ValidationIssue(
            code="missing_grain_key",
            field=key,
            message=f"Grain key is missing: {key}",
        )
        for key in missing_keys
    )

    for field in ("STATE", "ST_ABBR", "COUNTY"):
        if field in row:
            value = row[field]
            if not isinstance(value, str) or not value.strip():
                issues.append(
                    ValidationIssue(
                        code="blank_grain_key",
                        field=field,
                        message=f"Grain key is blank: {field}",
                    )
                )

    state_fips: str | None = None
    county_fips: str | None = None
    if "ST" in row:
        state_fips, issue = _validate_fips(row, "ST", _STATE_FIPS_PATTERN, 2)
        if issue is not None:
            issues.append(issue)
    if "STCNTY" in row:
        county_fips, issue = _validate_fips(
            row,
            "STCNTY",
            _COUNTY_FIPS_PATTERN,
            5,
        )
        if issue is not None:
            issues.append(issue)

    if state_fips is not None and county_fips is not None:
        if not county_fips.startswith(state_fips):
            issues.append(
                ValidationIssue(
                    code="fips_prefix_mismatch",
                    field="STCNTY",
                    message=(
                        f"County FIPS {county_fips} does not begin with state FIPS "
                        f"{state_fips}"
                    ),
                )
            )
        elif state_fips in TERRITORY_STATE_PREFIXES:
            issues.append(
                ValidationIssue(
                    code="territory_out_of_scope",
                    field="STCNTY",
                    message=(
                        f"Territory county FIPS is outside MVP scope: {county_fips}"
                    ),
                )
            )
        elif state_fips == "11" and county_fips != "11001":
            issues.append(
                ValidationIssue(
                    code="invalid_dc_fips",
                    field="STCNTY",
                    message=(
                        "District of Columbia must use county-equivalent FIPS "
                        f"11001, found {county_fips}"
                    ),
                )
            )

    if "GRASP_ID" in row and not _object_id_is_valid(row["GRASP_ID"]):
        value = row["GRASP_ID"]
        issues.append(
            ValidationIssue(
                code="invalid_object_id",
                field="GRASP_ID",
                message=f"GRASP_ID must be a positive integer value: {value!r}",
            )
        )

    return ValidationResult(issues=tuple(issues))


def validate_county_rows(rows: Iterable[Mapping[str, object]]) -> ValidationResult:
    """Validate every row and reject duplicate county FIPS deterministically."""
    issues: list[ValidationIssue] = []
    first_row_by_county: dict[str, int] = {}

    for row_number, row in enumerate(rows, start=1):
        issues.extend(validate_grain_keys(row).issues)
        county_fips = row.get("STCNTY")
        if not isinstance(county_fips, str):
            continue
        if _COUNTY_FIPS_PATTERN.fullmatch(county_fips) is None:
            continue
        first_row = first_row_by_county.setdefault(county_fips, row_number)
        if first_row != row_number:
            issues.append(
                ValidationIssue(
                    code="duplicate_county_fips",
                    field="STCNTY",
                    message=(
                        f"Duplicate county FIPS {county_fips} at row {row_number}; "
                        f"first seen at row {first_row}"
                    ),
                )
            )

    return ValidationResult(issues=tuple(issues))
