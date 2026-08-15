"""Raw-boundary contract for CMS Original Medicare Geographic Variation data.

This module validates source labels, CMS-declared type families, and raw grain
keys. It deliberately does not type metric values, normalize missingness, filter
geographies, or coerce county codes.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

SOURCE_ID: Final = "cms_om_gv"
CONTRACT_VERSION: Final = "cms_om_gv.raw.v2"

REQUIRED_COLUMNS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "YEAR": "NUMERIC",
        "BENE_GEO_LVL": "TEXT",
        "BENE_GEO_DESC": "TEXT",
        "BENE_GEO_CD": "TEXT",
        "BENE_AGE_LVL": "TEXT",
        "BENES_OM_CNT": "NUMERIC",
        "MA_PRTCPTN_RATE": "NUMERIC",
        "BENE_DUAL_PCT": "NUMERIC",
        "BENES_OP_DLYS_CNT": "NUMERIC",
        "BENES_OP_DLYS_PCT": "NUMERIC",
        "OP_DLYS_VISITS_PER_1000_BENES": "NUMERIC",
        "OP_DLYS_MDCR_STDZD_PYMT_PC": "NUMERIC",
        "ACUTE_HOSP_READMSN_PCT": "NUMERIC",
        "ER_VISITS_PER_1000_BENES": "NUMERIC",
    }
)

GRAIN_KEYS: Final = (
    "YEAR",
    "BENE_GEO_LVL",
    "BENE_GEO_DESC",
    "BENE_GEO_CD",
    "BENE_AGE_LVL",
)

_EXPECTED_TYPE_FAMILY: Final[Mapping[str, str]] = MappingProxyType(
    {
        name: "text" if declared_type == "TEXT" else "numeric"
        for name, declared_type in REQUIRED_COLUMNS.items()
    }
)
_COMPATIBLE_DECLARED_TYPES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "text": frozenset({"CHAR", "CHARACTER", "STRING", "TEXT", "VARCHAR"}),
        "numeric": frozenset(
            {
                "BIGINT",
                "DECIMAL",
                "DOUBLE",
                "FLOAT",
                "INT",
                "INTEGER",
                "NUMBER",
                "NUMERIC",
                "REAL",
            }
        ),
    }
)
_INTEGER_PATTERN: Final = re.compile(r"^[0-9]+$")
_BLANK_CODE_STATE_PSEUDO_ROWS: Final = frozenset({"TERRITORY", "ZZ"})


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    """A source column label and its CMS-declared type."""

    name: str
    declared_type: str


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
    additive_columns: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        """Return whether no blocking contract issue was found."""
        return not self.issues


def validate_schema(columns: Iterable[ColumnSchema]) -> ValidationResult:
    """Validate required labels and compatible declared type families.

    Extra source fields are compatible but reported. Required-field issues follow
    contract order, while additive labels are sorted, so logs are deterministic.
    """
    observed = tuple(columns)
    name_counts = Counter(column.name for column in observed)
    first_column_by_name: dict[str, ColumnSchema] = {}
    for column in observed:
        first_column_by_name.setdefault(column.name, column)

    issues: list[ValidationIssue] = []
    for field in REQUIRED_COLUMNS:
        count = name_counts[field]
        if count == 0:
            issues.append(
                ValidationIssue(
                    code="missing_required_column",
                    field=field,
                    message=f"Required column is missing: {field}",
                )
            )
            continue
        if count > 1:
            issues.append(
                ValidationIssue(
                    code="duplicate_required_column",
                    field=field,
                    message=f"Required column appears more than once: {field}",
                )
            )
            continue

        declared_type = first_column_by_name[field].declared_type.strip().upper()
        expected_family = _EXPECTED_TYPE_FAMILY[field]
        if declared_type not in _COMPATIBLE_DECLARED_TYPES[expected_family]:
            issues.append(
                ValidationIssue(
                    code="incompatible_required_type",
                    field=field,
                    message=(
                        f"Required column {field} has incompatible declared type "
                        f"{declared_type}; expected {expected_family}"
                    ),
                )
            )

    additive_columns = tuple(sorted(set(name_counts).difference(REQUIRED_COLUMNS)))
    return ValidationResult(
        issues=tuple(issues),
        additive_columns=additive_columns,
    )


def validate_grain_keys(row: Mapping[str, str]) -> ValidationResult:
    """Validate one raw-string source grain without coercing its values.

    CMS currently represents the national geography code as an empty string. It
    also emits blank codes for the state-level ``Territory`` and ``ZZ`` pseudo-
    rows. Those observed source representations are parseable only in those
    contexts; a blank county or ordinary-state code remains invalid.
    """
    issues: list[ValidationIssue] = []
    missing_keys = [key for key in GRAIN_KEYS if key not in row]
    for key in missing_keys:
        issues.append(
            ValidationIssue(
                code="missing_grain_key",
                field=key,
                message=f"Grain key is missing: {key}",
            )
        )

    year = row.get("YEAR")
    if year is not None:
        if not year.strip():
            issues.append(
                ValidationIssue(
                    code="blank_grain_key",
                    field="YEAR",
                    message="Grain key is blank: YEAR",
                )
            )
        elif _INTEGER_PATTERN.fullmatch(year) is None:
            issues.append(
                ValidationIssue(
                    code="unparseable_grain_key",
                    field="YEAR",
                    message=f"Grain key YEAR is not an integer: {year!r}",
                )
            )

    geography_level = row.get("BENE_GEO_LVL")
    if geography_level is not None and not geography_level.strip():
        issues.append(
            ValidationIssue(
                code="blank_grain_key",
                field="BENE_GEO_LVL",
                message="Grain key is blank: BENE_GEO_LVL",
            )
        )

    geography_description = row.get("BENE_GEO_DESC")
    if geography_description is not None and not geography_description.strip():
        issues.append(
            ValidationIssue(
                code="blank_grain_key",
                field="BENE_GEO_DESC",
                message="Grain key is blank: BENE_GEO_DESC",
            )
        )

    geography_code = row.get("BENE_GEO_CD")
    if geography_code is not None and not geography_code.strip():
        level = (geography_level or "").strip().upper()
        description = row.get("BENE_GEO_DESC", "").strip().upper()
        blank_code_is_observed = level == "NATIONAL" or (
            level == "STATE" and description in _BLANK_CODE_STATE_PSEUDO_ROWS
        )
        if not blank_code_is_observed:
            issues.append(
                ValidationIssue(
                    code="blank_grain_key",
                    field="BENE_GEO_CD",
                    message="Grain key is blank: BENE_GEO_CD",
                )
            )

    age_level = row.get("BENE_AGE_LVL")
    if age_level is not None and not age_level.strip():
        issues.append(
            ValidationIssue(
                code="blank_grain_key",
                field="BENE_AGE_LVL",
                message="Grain key is blank: BENE_AGE_LVL",
            )
        )

    return ValidationResult(issues=tuple(issues))
