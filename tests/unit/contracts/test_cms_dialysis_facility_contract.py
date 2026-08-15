"""Offline raw-boundary tests for the CMS dialysis facility source."""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from kidney_care_mart.contracts.cms_dialysis_facility import (
    CCN_CSV_HEADER,
    CONTRACT_VERSION,
    OUTCOME_FAMILIES,
    REQUIRED_FIELDS,
    ApiField,
    ValidationIssue,
    ValidationResult,
    validate_api_schema,
    validate_facility_rows,
    validate_required_mapping,
)
from kidney_care_mart.extract.cms_dialysis_facility import (
    DICTIONARY_BYTE_COUNT,
    DICTIONARY_SHA256,
    SCHEMA_EVIDENCE_SHA256,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_PATH = (
    Path(__file__).parents[2] / "fixtures" / "cms_dialysis_facility" / "minimal.csv"
)
SCHEMA_PATH = (
    REPOSITORY_ROOT / "docs" / "source-schemas" / "cms_dialysis_facility.schema.json"
)


def api_schema() -> list[ApiField]:
    """Return the required API fields plus one compatible additive field."""
    return [
        *(
            ApiField(
                api_field_name=field.api_field_name,
                csv_header=field.csv_header,
                declared_type="text",
            )
            for field in REQUIRED_FIELDS
        ),
        ApiField(
            api_field_name="synthetic_additive_note",
            csv_header="Synthetic Additive Note",
            declared_type="text",
        ),
    ]


def fixture_rows() -> list[dict[str, str]]:
    """Read every facility fixture value without type coercion."""
    with FIXTURE_PATH.open(encoding="utf-8", newline="") as fixture:
        return list(csv.DictReader(fixture))


def test_verified_required_mapping_and_representative_rows_pass() -> None:
    mapping_result = validate_required_mapping(REQUIRED_FIELDS)
    row_result = validate_facility_rows(fixture_rows())

    assert CONTRACT_VERSION == "cms_dialysis_facility.raw.v1"
    assert mapping_result.is_valid
    assert row_result.is_valid
    assert row_result.distinct_ccn_count == 3


@pytest.mark.parametrize("removed", REQUIRED_FIELDS, ids=lambda field: field.semantic)
def test_removing_each_required_mapping_reports_it(removed) -> None:
    observed = tuple(field for field in REQUIRED_FIELDS if field != removed)

    result = validate_required_mapping(observed)

    assert result.issues == (
        ValidationIssue(
            code="missing_required_mapping",
            field=removed.semantic,
            message=f"Required semantic mapping is missing: {removed.semantic}",
        ),
    )


def test_duplicate_csv_header_and_api_target_are_blocking() -> None:
    first, second, *remaining = REQUIRED_FIELDS
    duplicated = (
        first,
        replace(
            second,
            csv_header=first.csv_header,
            api_field_name=first.api_field_name,
        ),
        *remaining,
    )

    result = validate_required_mapping(duplicated)

    assert [issue.code for issue in result.issues] == [
        "duplicate_csv_mapping_target",
        "duplicate_api_mapping_target",
    ]


@pytest.mark.parametrize(
    ("semantic", "declared_type"),
    (
        ("ccn", "Num"),
        ("dialysis_stations", "Char"),
        ("certification_date", "Num"),
    ),
)
def test_incompatible_dictionary_type_family_is_blocking(
    semantic: str,
    declared_type: str,
) -> None:
    observed = tuple(
        replace(field, dictionary_declared_type=declared_type)
        if field.semantic == semantic
        else field
        for field in REQUIRED_FIELDS
    )

    result = validate_required_mapping(observed)

    assert result.issues[0].code == "incompatible_dictionary_type"
    assert result.issues[0].field == semantic


@pytest.mark.parametrize(
    ("attribute", "replacement", "expected_code"),
    (
        (
            "dictionary_label",
            "Friendly but unverified label",
            "incompatible_dictionary_label",
        ),
        (
            "dictionary_definition",
            "Friendly but unverified definition.",
            "incompatible_dictionary_definition",
        ),
        ("maximum_length", 999, "incompatible_dictionary_maximum_length"),
        ("type_family", "invented family", "incompatible_contract_type_family"),
        ("unit", "invented unit", "incompatible_dictionary_unit"),
        (
            "availability_companion",
            "invented_availability",
            "incompatible_availability_companion",
        ),
        ("outcome_family", "invented_family", "incompatible_outcome_family"),
        ("outcome_role", "invented_role", "incompatible_outcome_role"),
    ),
)
def test_pinned_dictionary_and_companion_metadata_drift_is_blocking(
    attribute: str,
    replacement: str | int,
    expected_code: str,
) -> None:
    target = next(
        field
        for field in REQUIRED_FIELDS
        if field.semantic == "survival_lower_confidence_limit"
    )
    observed = tuple(
        replace(field, **{attribute: replacement}) if field is target else field
        for field in REQUIRED_FIELDS
    )

    result = validate_required_mapping(observed)

    assert result.issues[0].code == expected_code
    assert result.issues[0].field == target.semantic


def test_friendly_label_similarity_cannot_hide_a_renamed_required_field() -> None:
    observed = tuple(
        replace(field, csv_header="Facility CCN") if field.semantic == "ccn" else field
        for field in REQUIRED_FIELDS
    )

    result = validate_required_mapping(observed)

    assert result.issues == (
        ValidationIssue(
            code="incompatible_csv_mapping",
            field="ccn",
            message=(
                "Required semantic ccn maps to CSV header 'Facility CCN'; "
                f"expected {CCN_CSV_HEADER!r}"
            ),
        ),
    )


def test_api_schema_is_one_to_one_and_reports_sorted_additions() -> None:
    observed = [
        ApiField("z_addition", "Z Addition", "text"),
        *api_schema(),
        ApiField("a_addition", "A Addition", "text"),
    ]

    result = validate_api_schema(observed)

    assert result.is_valid
    assert result.additive_fields == (
        "A Addition",
        "Synthetic Additive Note",
        "Z Addition",
    )


def test_duplicate_additive_csv_header_is_blocking_metadata_drift() -> None:
    observed = [
        *api_schema(),
        ApiField(
            api_field_name="second_synthetic_additive",
            csv_header="Synthetic Additive Note",
            declared_type="text",
        ),
    ]

    result = validate_api_schema(observed)

    assert result.issues == (
        ValidationIssue(
            code="duplicate_additive_csv_header",
            field="Synthetic Additive Note",
            message=(
                "Compatible additive CSV header appears more than once: "
                "Synthetic Additive Note"
            ),
        ),
    )


def test_api_required_field_removal_duplicate_and_type_drift_block() -> None:
    observed = api_schema()
    ccn = observed[0]
    observed[0] = replace(ccn, declared_type="integer")
    observed.append(replace(ccn))

    result = validate_api_schema(observed)

    assert [issue.code for issue in result.issues] == [
        "duplicate_required_api_field",
    ]

    missing = validate_api_schema(observed[1:-1])
    assert missing.issues[0].code == "missing_required_api_field"


def test_all_three_outcome_families_have_every_required_companion() -> None:
    required_roles = {
        "period",
        "availability",
        "category",
        "denominator",
        "estimate",
        "lower_confidence_limit",
        "upper_confidence_limit",
    }

    assert set(OUTCOME_FAMILIES) == {
        "survival",
        "hospitalization",
        "readmission",
    }
    assert all(
        {field.outcome_role for field in fields} == required_roles
        for fields in OUTCOME_FAMILIES.values()
    )


def test_leading_zero_and_raw_business_location_strings_survive() -> None:
    rows = fixture_rows()
    first = rows[0]

    assert first[CCN_CSV_HEADER] == "012345"
    assert isinstance(first[CCN_CSV_HEADER], str)
    assert first["ZIP Code"] == "01234"
    assert first["Address Line 2"] == ""
    assert first["# of Dialysis Stations"] == "12"
    assert rows[1]["# of Dialysis Stations"] == "0"
    assert rows[2]["State"] == "PR"
    assert rows[2]["County/Parish"] == "La Salle Parish"


@pytest.mark.parametrize("ccn", ("", "   "))
def test_blank_ccn_is_blocking(ccn: str) -> None:
    rows = fixture_rows()
    rows[1][CCN_CSV_HEADER] = ccn

    result = validate_facility_rows(rows)

    assert result.issues[0].code == "blank_ccn"


@pytest.mark.parametrize(
    "ccn",
    ("12345A", "\uff11\uff12\uff13\uff14\uff15\uff16", "12345678901", " 123456"),
)
def test_nonconforming_ccn_text_is_blocking_without_coercion(ccn: str) -> None:
    rows = fixture_rows()
    rows[1][CCN_CSV_HEADER] = ccn

    result = validate_facility_rows(rows)

    assert result.issues == (
        ValidationIssue(
            code="invalid_ccn_format",
            field=CCN_CSV_HEADER,
            message=f"CCN must be 1-10 ASCII-digit text at source row 3: {ccn!r}",
        ),
    )


def test_duplicate_ccn_is_blocking_without_deduplication() -> None:
    rows = fixture_rows()
    rows[2][CCN_CSV_HEADER] = rows[0][CCN_CSV_HEADER]

    result = validate_facility_rows(rows)

    assert result.issues == (
        ValidationIssue(
            code="duplicate_ccn",
            field=CCN_CSV_HEADER,
            message="Duplicate CCN '012345' at source row 4; first seen at row 2",
        ),
    )


def test_missing_nonkey_tokens_remain_distinct_from_zero() -> None:
    values = {value for row in fixture_rows() for value in row.values()}

    assert "" in values
    assert "0" in values


def test_normalized_schema_snapshot_and_dictionary_are_hashed() -> None:
    snapshot = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    observed = snapshot["observed_schema"]["csv_headers_in_source_order"]
    api_fields = snapshot["observed_schema"]["api_fields_in_source_order"]
    mapping = snapshot["required_semantic_mapping"]
    dictionary = snapshot["dictionary"]

    assert len(observed) == len(api_fields) == 142
    assert len(observed) == len(set(observed))
    assert [field["semantic"] for field in mapping] == [
        field.semantic for field in REQUIRED_FIELDS
    ]
    assert mapping == [asdict(field) for field in REQUIRED_FIELDS]
    assert snapshot["additive_csv_headers"] == sorted(
        set(observed) - {field.csv_header for field in REQUIRED_FIELDS}
    )

    hash_payload = {
        key: value
        for key, value in snapshot.items()
        if key not in {"retrieval", "schema_sha256"}
    }
    canonical = json.dumps(
        hash_payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    assert hashlib.sha256(canonical).hexdigest() == snapshot["schema_sha256"]
    assert snapshot["schema_sha256"] == SCHEMA_EVIDENCE_SHA256

    dictionary_path = REPOSITORY_ROOT / dictionary["local_path"]
    content = dictionary_path.read_bytes()
    assert content.startswith(b"%PDF-")
    assert len(content) == dictionary["byte_count"] == DICTIONARY_BYTE_COUNT
    assert (
        hashlib.sha256(content).hexdigest() == dictionary["sha256"] == DICTIONARY_SHA256
    )


def test_validation_result_is_structured_and_immutable() -> None:
    result = validate_required_mapping(())

    assert isinstance(result, ValidationResult)
    assert result.issues
    assert all(isinstance(issue, ValidationIssue) for issue in result.issues)
    with pytest.raises(AttributeError):
        result.issues = ()
