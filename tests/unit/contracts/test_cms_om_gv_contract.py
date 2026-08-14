"""Offline contract tests for the CMS Original Medicare source.

The CSV fixture is synthetic and representative. It preserves source-shaped raw
strings but does not report real county measurements.
"""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from kidney_care_mart.contracts.cms_om_gv import (
    GRAIN_KEYS,
    REQUIRED_COLUMNS,
    ColumnSchema,
    ValidationIssue,
    ValidationResult,
    validate_grain_keys,
    validate_schema,
)

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "cms_om_gv" / "minimal.csv"
REPOSITORY_ROOT = Path(__file__).parents[3]
SCHEMA_PATH = REPOSITORY_ROOT / "docs" / "source-schemas" / "cms_om_gv.schema.json"


def required_schema() -> list[ColumnSchema]:
    """Return the verified required subset using current CMS declared types."""
    return [
        ColumnSchema(name=name, declared_type=declared_type)
        for name, declared_type in REQUIRED_COLUMNS.items()
    ]


def valid_county_row() -> dict[str, str]:
    """Return a minimally valid raw county grain mapping."""
    return {
        "YEAR": "2024",
        "BENE_GEO_LVL": "County",
        "BENE_GEO_DESC": "AL-Synthetic Autauga",
        "BENE_GEO_CD": "01001",
        "BENE_AGE_LVL": "All",
    }


def test_verified_schema_and_representative_fixture_pass() -> None:
    """The verified required subset and every fixture grain are compatible."""
    schema_result = validate_schema(required_schema())

    with FIXTURE_PATH.open(newline="", encoding="utf-8") as fixture_file:
        reader = csv.DictReader(fixture_file)
        rows = list(reader)

    assert schema_result.is_valid
    assert schema_result.issues == ()
    assert schema_result.additive_columns == ()
    assert rows
    assert all(validate_grain_keys(row).is_valid for row in rows)


@pytest.mark.parametrize("removed_column", REQUIRED_COLUMNS)
def test_removing_each_required_column_reports_it(removed_column: str) -> None:
    """Every required field removal blocks the contract deterministically."""
    observed = [column for column in required_schema() if column.name != removed_column]

    result = validate_schema(observed)

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="missing_required_column",
            field=removed_column,
            message=f"Required column is missing: {removed_column}",
        ),
    )


def test_additive_column_passes_and_is_reported() -> None:
    """An additive field is compatible and visible to future audit logs."""
    observed = [
        *required_schema(),
        ColumnSchema(name="NEW_CMS_FIELD", declared_type="TEXT"),
    ]

    result = validate_schema(observed)

    assert result.is_valid
    assert result.issues == ()
    assert result.additive_columns == ("NEW_CMS_FIELD",)


def test_additive_columns_are_reported_in_deterministic_order() -> None:
    """Source additions do not depend on input ordering."""
    observed = [
        ColumnSchema(name="Z_FIELD", declared_type="TEXT"),
        *required_schema(),
        ColumnSchema(name="A_FIELD", declared_type="NUMERIC"),
    ]

    result = validate_schema(observed)

    assert result.is_valid
    assert result.additive_columns == ("A_FIELD", "Z_FIELD")


@pytest.mark.parametrize("duplicated_column", REQUIRED_COLUMNS)
def test_duplicating_each_required_header_fails(duplicated_column: str) -> None:
    """A duplicate required header cannot be hidden by mapping semantics."""
    observed = [
        *required_schema(),
        ColumnSchema(
            name=duplicated_column,
            declared_type=REQUIRED_COLUMNS[duplicated_column],
        ),
    ]

    result = validate_schema(observed)

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="duplicate_required_column",
            field=duplicated_column,
            message=f"Required column appears more than once: {duplicated_column}",
        ),
    )


def test_incompatible_required_type_fails() -> None:
    """A required numeric field cannot silently become text."""
    observed = [
        ColumnSchema(
            name=column.name,
            declared_type=(
                "TEXT" if column.name == "BENES_OP_DLYS_PCT" else column.declared_type
            ),
        )
        for column in required_schema()
    ]

    result = validate_schema(observed)

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="incompatible_required_type",
            field="BENES_OP_DLYS_PCT",
            message=(
                "Required column BENES_OP_DLYS_PCT has incompatible declared "
                "type TEXT; expected numeric"
            ),
        ),
    )


@pytest.mark.parametrize("missing_key", GRAIN_KEYS)
def test_every_grain_key_is_required(missing_key: str) -> None:
    """A source row without any declared grain key is invalid."""
    row = valid_county_row()
    row.pop(missing_key)

    result = validate_grain_keys(row)

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="missing_grain_key",
            field=missing_key,
            message=f"Grain key is missing: {missing_key}",
        ),
    )


def test_non_integer_year_fails_grain_parsing() -> None:
    """YEAR must be an integer-shaped raw source string."""
    row = valid_county_row()
    row["YEAR"] = "2024.0"

    result = validate_grain_keys(row)

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="unparseable_grain_key",
            field="YEAR",
            message="Grain key YEAR is not an integer: '2024.0'",
        ),
    )


@pytest.mark.parametrize(
    "blank_key",
    ("BENE_GEO_LVL", "BENE_GEO_DESC", "BENE_GEO_CD", "BENE_AGE_LVL"),
)
def test_blank_county_grain_values_fail(blank_key: str) -> None:
    """Blank county grain values cannot enter the contract unnoticed."""
    row = valid_county_row()
    row[blank_key] = ""

    result = validate_grain_keys(row)

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="blank_grain_key",
            field=blank_key,
            message=f"Grain key is blank: {blank_key}",
        ),
    )


def test_official_national_blank_geography_code_is_parseable() -> None:
    """CMS represents the current national code as an empty raw string."""
    row = valid_county_row()
    row.update(
        {
            "BENE_GEO_LVL": "National",
            "BENE_GEO_DESC": "National",
            "BENE_GEO_CD": "",
        }
    )

    result = validate_grain_keys(row)

    assert result.is_valid
    assert result.issues == ()


def test_leading_zero_county_code_remains_a_raw_string() -> None:
    """CSV reading cannot erase the leading zero from county FIPS."""
    with FIXTURE_PATH.open(newline="", encoding="utf-8") as fixture_file:
        first_row = next(csv.DictReader(fixture_file))

    assert first_row["BENE_GEO_CD"] == "01001"
    assert isinstance(first_row["BENE_GEO_CD"], str)


def test_fixture_preserves_distinct_raw_missingness_and_zero_tokens() -> None:
    """The fixture keeps suppression, missingness, and numeric zero distinct."""
    with FIXTURE_PATH.open(newline="", encoding="utf-8") as fixture_file:
        raw_values = {value for row in csv.reader(fixture_file) for value in row}

    assert {"*", "", "NA", "0"} <= raw_values


def test_normalized_schema_snapshot_is_complete_and_hashed() -> None:
    """Committed evidence covers the full observed schema deterministically."""
    snapshot = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    observed = snapshot["observed_schema"]["columns_in_source_order"]
    additive = snapshot["additive_columns"]
    mapping = snapshot["required_semantic_mapping"]
    type_encoding = snapshot["observed_schema"]["declared_type_encoding"]

    assert len(observed) == snapshot["observed_schema"]["column_count"] == 246
    assert len(observed) == len(set(observed))
    assert [field["source_label"] for field in mapping] == list(REQUIRED_COLUMNS)
    assert {field["source_label"]: field["declared_type"] for field in mapping} == dict(
        REQUIRED_COLUMNS
    )
    assert additive == [name for name in observed if name not in REQUIRED_COLUMNS]
    assert type_encoding["counts"] == {"NUMERIC": 242, "TEXT": 4}
    assert sum(type_encoding["counts"].values()) == len(observed)

    hash_payload = {
        key: value
        for key, value in snapshot.items()
        if key not in {"retrieval", "schema_sha256"}
    }
    canonical_payload = json.dumps(
        hash_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    assert hashlib.sha256(canonical_payload).hexdigest() == snapshot["schema_sha256"]


def test_pinned_dictionary_matches_recorded_hash_and_size() -> None:
    """The retained official dictionary matches normalized provenance."""
    snapshot = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    dictionary = snapshot["dictionary"]
    dictionary_path = REPOSITORY_ROOT / dictionary["local_path"]
    content = dictionary_path.read_bytes()

    assert len(content) == dictionary["byte_count"]
    assert content.startswith(b"%PDF-")
    assert hashlib.sha256(content).hexdigest() == dictionary["sha256"]


def test_validation_result_is_structured_and_immutable() -> None:
    """Validation output is suitable for logs without parsing assertion text."""
    result = validate_schema([])

    assert isinstance(result, ValidationResult)
    assert result.issues
    assert all(isinstance(issue, ValidationIssue) for issue in result.issues)
    with pytest.raises(AttributeError):
        result.issues = ()
