"""Offline contract tests for the CDC/ATSDR SVI 2022 county source.

The CSV fixture is synthetic and representative. It preserves source-shaped raw
strings but does not report observations about the named geographies.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from kidney_care_mart.contracts.cdc_svi_county_2022 import (
    EXPECTED_LAYER_ID,
    EXPECTED_LAYER_NAME,
    EXPECTED_OBJECT_ID_FIELD,
    GRAIN_KEYS,
    REQUIRED_FIELDS,
    ArcGisField,
    ValidationIssue,
    ValidationResult,
    validate_county_rows,
    validate_grain_keys,
    validate_layer_schema,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
FIXTURE_PATH = (
    REPOSITORY_ROOT / "tests" / "fixtures" / "cdc_svi_county_2022" / "minimal.csv"
)
SCHEMA_PATH = (
    REPOSITORY_ROOT / "docs" / "source-schemas" / "cdc_svi_county_2022.schema.json"
)


def required_schema() -> list[ArcGisField]:
    """Return the contract's required subset with compatible declared types."""
    representative_type = {
        "string": "esriFieldTypeString",
        "numeric": "esriFieldTypeDouble",
        "oid": "esriFieldTypeOID",
    }
    return [
        ArcGisField(name=name, declared_type=representative_type[type_family])
        for name, type_family in REQUIRED_FIELDS.items()
    ]


def valid_county_row() -> dict[str, object]:
    """Return a minimally valid county grain from the synthetic fixture."""
    return {
        "ST": "01",
        "STATE": "Synthetic Alabama",
        "ST_ABBR": "AL",
        "STCNTY": "01001",
        "COUNTY": "Synthetic County A",
        "GRASP_ID": "1",
    }


def load_fixture() -> list[dict[str, str]]:
    """Read the representative raw fixture without type inference."""
    with FIXTURE_PATH.open(newline="", encoding="utf-8") as fixture_file:
        return list(csv.DictReader(fixture_file))


def observed_schema() -> tuple[dict[str, object], list[ArcGisField]]:
    """Read complete normalized official field metadata."""
    snapshot = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    observed = snapshot["observed_schema"]
    declared_types = {
        name: declared_type
        for declared_type, names in observed["declared_type_encoding"][
            "fields_by_type"
        ].items()
        for name in names
    }
    fields = [
        ArcGisField(name=name, declared_type=declared_types[name])
        for name in observed["fields_in_source_order"]
    ]
    return snapshot, fields


def test_verified_schema_and_representative_fixture_pass() -> None:
    """The official schema and every fixture grain satisfy the raw contract."""
    snapshot, fields = observed_schema()
    observed = snapshot["observed_schema"]

    schema_result = validate_layer_schema(
        layer_id=observed["layer_id"],
        layer_name=observed["layer_name"],
        object_id_field=observed["object_id_field"],
        fields=fields,
    )
    grain_result = validate_county_rows(load_fixture())

    assert schema_result.is_valid
    assert schema_result.issues == ()
    assert schema_result.additive_fields == tuple(snapshot["additive_fields"])
    assert grain_result.is_valid
    assert grain_result.issues == ()


@pytest.mark.parametrize("removed_field", REQUIRED_FIELDS)
def test_removing_each_required_field_reports_it(removed_field: str) -> None:
    """Every required field removal blocks the contract deterministically."""
    observed = [field for field in required_schema() if field.name != removed_field]

    result = validate_layer_schema(
        layer_id=EXPECTED_LAYER_ID,
        layer_name=EXPECTED_LAYER_NAME,
        object_id_field=EXPECTED_OBJECT_ID_FIELD,
        fields=observed,
    )

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="missing_required_field",
            field=removed_field,
            message=f"Required ArcGIS field is missing: {removed_field}",
        ),
    )


@pytest.mark.parametrize("duplicated_field", REQUIRED_FIELDS)
def test_duplicating_each_required_field_fails(duplicated_field: str) -> None:
    """A duplicate required label cannot be hidden by mapping semantics."""
    fields = required_schema()
    fields.append(next(field for field in fields if field.name == duplicated_field))

    result = validate_layer_schema(
        layer_id=EXPECTED_LAYER_ID,
        layer_name=EXPECTED_LAYER_NAME,
        object_id_field=EXPECTED_OBJECT_ID_FIELD,
        fields=fields,
    )

    assert not result.is_valid
    assert result.issues == (
        ValidationIssue(
            code="duplicate_required_field",
            field=duplicated_field,
            message=f"Required ArcGIS field appears more than once: {duplicated_field}",
        ),
    )


@pytest.mark.parametrize(
    ("field_name", "bad_type", "expected_family"),
    [
        ("STCNTY", "esriFieldTypeDouble", "string"),
        ("RPL_THEMES", "esriFieldTypeString", "numeric"),
        ("GRASP_ID", "esriFieldTypeInteger", "oid"),
    ],
)
def test_incompatible_required_type_family_fails(
    field_name: str,
    bad_type: str,
    expected_family: str,
) -> None:
    """String, numeric, and object-ID fields cannot change family silently."""
    fields = [
        ArcGisField(
            name=field.name,
            declared_type=bad_type if field.name == field_name else field.declared_type,
        )
        for field in required_schema()
    ]

    result = validate_layer_schema(
        layer_id=EXPECTED_LAYER_ID,
        layer_name=EXPECTED_LAYER_NAME,
        object_id_field=EXPECTED_OBJECT_ID_FIELD,
        fields=fields,
    )

    assert result.issues == (
        ValidationIssue(
            code="incompatible_required_type",
            field=field_name,
            message=(
                f"Required ArcGIS field {field_name} has incompatible declared "
                f"type {bad_type}; expected {expected_family}"
            ),
        ),
    )


def test_additive_fields_pass_and_are_reported_in_sorted_order() -> None:
    """Source additions remain compatible and visible to audit logs."""
    fields = [
        ArcGisField(name="Z_NEW_FIELD", declared_type="esriFieldTypeDouble"),
        *required_schema(),
        ArcGisField(name="A_NEW_FIELD", declared_type="esriFieldTypeString"),
    ]

    result = validate_layer_schema(
        layer_id=EXPECTED_LAYER_ID,
        layer_name=EXPECTED_LAYER_NAME,
        object_id_field=EXPECTED_OBJECT_ID_FIELD,
        fields=fields,
    )

    assert result.is_valid
    assert result.additive_fields == ("A_NEW_FIELD", "Z_NEW_FIELD")


@pytest.mark.parametrize(
    ("field_name", "value", "code"),
    [
        ("layer_id", 2, "unexpected_layer_id"),
        ("layer_name", "SVI2022 US tract", "unexpected_layer_name"),
        ("object_id_field", "OBJECTID", "unexpected_object_id_field"),
    ],
)
def test_wrong_layer_identity_or_object_id_field_fails(
    field_name: str,
    value: object,
    code: str,
) -> None:
    """A similarly shaped tract or differently keyed layer is not accepted."""
    arguments = {
        "layer_id": EXPECTED_LAYER_ID,
        "layer_name": EXPECTED_LAYER_NAME,
        "object_id_field": EXPECTED_OBJECT_ID_FIELD,
        "fields": required_schema(),
    }
    arguments[field_name] = value

    result = validate_layer_schema(**arguments)

    assert not result.is_valid
    assert result.issues[0].code == code


@pytest.mark.parametrize("missing_key", GRAIN_KEYS)
def test_every_grain_key_is_required(missing_key: str) -> None:
    """A row missing any declared grain/audit key is invalid."""
    row = valid_county_row()
    row.pop(missing_key)

    result = validate_grain_keys(row)

    assert result.issues == (
        ValidationIssue(
            code="missing_grain_key",
            field=missing_key,
            message=f"Grain key is missing: {missing_key}",
        ),
    )


@pytest.mark.parametrize("blank_key", ("STATE", "ST_ABBR", "COUNTY"))
def test_blank_geography_labels_fail(blank_key: str) -> None:
    """Source geography labels remain present for lineage and auditability."""
    row = valid_county_row()
    row[blank_key] = "   "

    result = validate_grain_keys(row)

    assert result.issues == (
        ValidationIssue(
            code="blank_grain_key",
            field=blank_key,
            message=f"Grain key is blank: {blank_key}",
        ),
    )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("ST", "1"),
        ("ST", "\u0660\u0661"),
        ("ST", 1),
        ("STCNTY", "1001"),
        ("STCNTY", "\uff10\uff11\uff10\uff10\uff11"),
        ("STCNTY", 1001),
    ],
)
def test_fips_must_be_fixed_width_ascii_text(
    field_name: str,
    bad_value: object,
) -> None:
    """No numeric or Unicode-digit coercion may satisfy the county-key policy."""
    row = valid_county_row()
    row[field_name] = bad_value

    result = validate_grain_keys(row)

    assert not result.is_valid
    assert result.issues[0].code == "invalid_fips"
    assert result.issues[0].field == field_name


def test_state_and_county_fips_prefix_must_agree() -> None:
    """The source state cannot disagree with the county's first two digits."""
    row = valid_county_row()
    row["ST"] = "02"

    result = validate_grain_keys(row)

    assert result.issues == (
        ValidationIssue(
            code="fips_prefix_mismatch",
            field="STCNTY",
            message="County FIPS 01001 does not begin with state FIPS 02",
        ),
    )


@pytest.mark.parametrize("territory_prefix", ("60", "66", "69", "72", "78"))
def test_territory_prefixes_are_out_of_scope(territory_prefix: str) -> None:
    """Territories cannot enter the MVP U.S. county contract."""
    row = valid_county_row()
    row["ST"] = territory_prefix
    row["STCNTY"] = f"{territory_prefix}001"

    result = validate_grain_keys(row)

    assert result.issues == (
        ValidationIssue(
            code="territory_out_of_scope",
            field="STCNTY",
            message=f"Territory county FIPS is outside MVP scope: {territory_prefix}001",
        ),
    )


@pytest.mark.parametrize("bad_object_id", ("0", "-1", "1.0", " 1 ", 0, 1.0, True))
def test_object_id_must_be_a_positive_integer_value(bad_object_id: object) -> None:
    """Transport ordering requires a positive integer without fuzzy coercion."""
    row = valid_county_row()
    row["GRASP_ID"] = bad_object_id

    result = validate_grain_keys(row)

    assert result.issues == (
        ValidationIssue(
            code="invalid_object_id",
            field="GRASP_ID",
            message=f"GRASP_ID must be a positive integer value: {bad_object_id!r}",
        ),
    )


def test_integer_object_id_from_live_json_is_accepted() -> None:
    """ArcGIS JSON integers and raw lexical integers share one contract."""
    row = valid_county_row()
    row["GRASP_ID"] = 1

    assert validate_grain_keys(row).is_valid


def test_duplicate_county_fips_fails_complete_row_validation() -> None:
    """No observed row set may silently deduplicate the county grain."""
    rows = [valid_county_row(), {**valid_county_row(), "GRASP_ID": "2"}]

    result = validate_county_rows(rows)

    assert result.issues == (
        ValidationIssue(
            code="duplicate_county_fips",
            field="STCNTY",
            message="Duplicate county FIPS 01001 at row 2; first seen at row 1",
        ),
    )


def test_fixture_preserves_leading_zero_dc_sentinel_and_boundaries() -> None:
    """The fixture prepares later typing rules without implementing them here."""
    rows = load_fixture()
    raw_values = {value for row in rows for value in row.values()}

    assert rows[0]["STCNTY"] == "01001"
    assert rows[1]["STCNTY"] == "11001"
    assert {"-999", "0", "0.75", "1", "1.25"} <= raw_values


def test_normalized_schema_is_complete_and_hashed() -> None:
    """Committed evidence covers every observed ArcGIS field and type."""
    snapshot, fields = observed_schema()
    observed = snapshot["observed_schema"]
    type_encoding = observed["declared_type_encoding"]
    grouped_names = [
        name for names in type_encoding["fields_by_type"].values() for name in names
    ]

    assert len(fields) == observed["field_count"] == 161
    assert len(grouped_names) == len(set(grouped_names)) == len(fields)
    assert set(grouped_names) == set(observed["fields_in_source_order"])
    assert sum(type_encoding["counts"].values()) == len(fields)
    assert [
        item["source_label"] for item in snapshot["required_semantic_mapping"]
    ] == list(REQUIRED_FIELDS)
    assert snapshot["additive_fields"] == sorted(
        set(observed["fields_in_source_order"]).difference(REQUIRED_FIELDS)
    )

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


def test_pinned_documentation_matches_recorded_hash_and_size() -> None:
    """The retained official PDF matches normalized provenance."""
    snapshot = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    documentation = snapshot["documentation"]
    document_path = REPOSITORY_ROOT / documentation["local_path"]
    content = document_path.read_bytes()

    assert content.startswith(b"%PDF-")
    assert len(content) == documentation["byte_count"]
    assert hashlib.sha256(content).hexdigest() == documentation["sha256"]


def test_validation_result_is_structured_and_immutable() -> None:
    """Validation output is suitable for logs without parsing assertion text."""
    result = validate_layer_schema(
        layer_id=EXPECTED_LAYER_ID,
        layer_name=EXPECTED_LAYER_NAME,
        object_id_field=EXPECTED_OBJECT_ID_FIELD,
        fields=[],
    )

    assert isinstance(result, ValidationResult)
    assert result.issues
    assert all(isinstance(issue, ValidationIssue) for issue in result.issues)
    with pytest.raises(AttributeError):
        result.issues = ()
