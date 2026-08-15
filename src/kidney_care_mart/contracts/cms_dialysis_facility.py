"""Raw-boundary contract for the CMS Dialysis Facility listing.

The contract maps the bounded MVP concepts across the July 2026 dictionary,
Provider Data API field slugs, and full-CSV headers. It validates only raw
schema compatibility and one textual CCN per row. Typing, availability-code
interpretation, geography assignment, and metric calculation are deferred.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

SOURCE_ID: Final = "cms_dialysis_facility"
CONTRACT_VERSION: Final = "cms_dialysis_facility.raw.v1"
CCN_CSV_HEADER: Final = "CMS Certification Number (CCN)"
CCN_API_FIELD: Final = "cms_certification_number_ccn"
_CCN_PATTERN: Final = re.compile(r"^[0-9]{1,10}$", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class RequiredField:
    """One verified semantic mapping across official CMS source surfaces."""

    semantic: str
    dictionary_variable: str
    dictionary_label: str
    dictionary_definition: str
    dictionary_declared_type: str
    maximum_length: int | None
    type_family: str
    unit: str
    csv_header: str
    api_field_name: str
    availability_companion: str | None = None
    outcome_family: str | None = None
    outcome_role: str | None = None


@dataclass(frozen=True, slots=True)
class ApiField:
    """One ordered Provider Data API field and its full-CSV label."""

    api_field_name: str
    csv_header: str
    declared_type: str


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One deterministic contract issue suitable for audit logging."""

    code: str
    field: str
    message: str


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Structured immutable output from schema or raw-grain validation."""

    issues: tuple[ValidationIssue, ...] = ()
    additive_fields: tuple[str, ...] = ()
    distinct_ccn_count: int = 0

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _required(
    semantic: str,
    dictionary_variable: str,
    dictionary_label: str,
    dictionary_definition: str,
    dictionary_declared_type: str,
    maximum_length: int | None,
    type_family: str,
    unit: str,
    csv_header: str,
    api_field_name: str,
    *,
    availability_companion: str | None = None,
    outcome_family: str | None = None,
    outcome_role: str | None = None,
) -> RequiredField:
    return RequiredField(
        semantic=semantic,
        dictionary_variable=dictionary_variable,
        dictionary_label=dictionary_label,
        dictionary_definition=dictionary_definition,
        dictionary_declared_type=dictionary_declared_type,
        maximum_length=maximum_length,
        type_family=type_family,
        unit=unit,
        csv_header=csv_header,
        api_field_name=api_field_name,
        availability_companion=availability_companion,
        outcome_family=outcome_family,
        outcome_role=outcome_role,
    )


REQUIRED_FIELDS: Final = (
    _required(
        "ccn",
        "PROVFS",
        "CMS Certification Number (CCN)",
        "The numeric code used to identify the provider.",
        "Char",
        10,
        "text",
        "identifier",
        CCN_CSV_HEADER,
        CCN_API_FIELD,
    ),
    _required(
        "facility_name",
        "QDFC_PROVNAME",
        "CMS Provider Name",
        "The name of the facility.",
        "Char",
        200,
        "text",
        "label",
        "Facility Name",
        "facility_name",
    ),
    _required(
        "address_line_1",
        "PHYADDR1",
        "Address Line 1",
        "The first line of the public business address.",
        "Char",
        60,
        "text",
        "address",
        "Address Line 1",
        "address_line_1",
    ),
    _required(
        "address_line_2",
        "PHYADDR2",
        "Address Line 2",
        "The optional second line of the public business address.",
        "Char",
        60,
        "text",
        "address",
        "Address Line 2",
        "address_line_2",
    ),
    _required(
        "city",
        "PHYCITY",
        "City/Town",
        "The city corresponding to the facility.",
        "Char",
        30,
        "text",
        "label",
        "City/Town",
        "citytown",
    ),
    _required(
        "state",
        "STATE",
        "State",
        "The postal code for the facility state.",
        "Char",
        2,
        "text",
        "postal_code",
        "State",
        "state",
    ),
    _required(
        "zip_code",
        "PHYZIP",
        "Zip Code",
        "The postal ZIP code corresponding to the facility.",
        "Char",
        5,
        "text",
        "postal_code",
        "ZIP Code",
        "zip_code",
    ),
    _required(
        "source_county",
        "PHYCOUNTY",
        "County/Parish",
        "The source county name corresponding to the facility.",
        "Char",
        60,
        "text",
        "label",
        "County/Parish",
        "countyparish",
    ),
    _required(
        "telephone",
        "PHONENUM",
        "Telephone Number",
        "The public business telephone number for the facility.",
        "Char",
        14,
        "text",
        "telephone",
        "Telephone Number",
        "telephone_number",
    ),
    _required(
        "ownership_status",
        "OWNTYPE",
        "Profit or Non-Profit",
        "Whether the facility operates as a for-profit or non-profit business.",
        "Char",
        50,
        "text",
        "category",
        "Profit or Non-Profit",
        "profit_or_nonprofit",
    ),
    _required(
        "chain_owned",
        "CHAINYN",
        "Chain Owned",
        "Whether the facility is owned or managed by a chain organization.",
        "Char",
        3,
        "text",
        "category",
        "Chain Owned",
        "chain_owned",
    ),
    _required(
        "chain_organization",
        "CHAINNAM",
        "Chain Organization",
        "The chain organization name when applicable.",
        "Char",
        50,
        "text",
        "label",
        "Chain Organization",
        "chain_organization",
    ),
    _required(
        "dialysis_stations",
        "TOTSTAS",
        "# of Dialysis Stations",
        "The total number of dialysis stations at the facility.",
        "Int",
        None,
        "integer",
        "stations",
        "# of Dialysis Stations",
        "of_dialysis_stations",
    ),
    _required(
        "in_center_hemodialysis",
        "HD",
        "Offers in-center hemodialysis",
        "Whether the facility offers in-center hemodialysis.",
        "Text",
        5,
        "text",
        "category",
        "Offers in-center hemodialysis",
        "offers_incenter_hemodialysis",
    ),
    _required(
        "peritoneal_dialysis",
        "PD",
        "Offers peritoneal dialysis",
        "Whether the facility offers peritoneal dialysis.",
        "Text",
        5,
        "text",
        "category",
        "Offers peritoneal dialysis",
        "offers_peritoneal_dialysis",
    ),
    _required(
        "home_hemodialysis_training",
        "HOMEHD",
        "Offers home hemodialysis training.",
        "Whether the facility offers home hemodialysis training.",
        "Text",
        5,
        "text",
        "category",
        "Offers home hemodialysis training",
        "offers_home_hemodialysis_training",
    ),
    _required(
        "certification_date",
        "CERTDATE",
        "Certification Date",
        "The initial or recertification date for the facility.",
        "Datetime",
        None,
        "date",
        "date",
        "Certification Date",
        "certification_date",
    ),
    _required(
        "five_star_period",
        "DATE_FIVE_STAR",
        "Five Star Date",
        "The data collection period for the quality-of-care star rating.",
        "Char",
        19,
        "text",
        "period",
        "Five Star Date",
        "five_star_date",
        availability_companion="five_star_availability",
    ),
    _required(
        "five_star_rating",
        "FIVE_STAR",
        "Five Star",
        "The quality-of-care star rating for the facility.",
        "Num",
        8,
        "numeric",
        "rating",
        "Five Star",
        "five_star",
        availability_companion="five_star_availability",
    ),
    _required(
        "five_star_availability",
        "FIVE_STAR_C",
        "Five Star Data Availability Code",
        "Whether rating data are available or the reason they are unavailable.",
        "Char",
        3,
        "text",
        "availability_code",
        "Five Star Data Availability Code",
        "five_star_data_availability_code",
    ),
    _required(
        "survival_period",
        "DATE_SMR",
        "SMR Date",
        "The data collection period for the patient survival summary.",
        "Char",
        19,
        "text",
        "period",
        "SMR Date",
        "smr_date",
        availability_companion="survival_availability",
        outcome_family="survival",
        outcome_role="period",
    ),
    _required(
        "survival_availability",
        "PTSURV_C",
        "Patient Survival Data Availability Code",
        "Whether survival data are available or the reason they are unavailable.",
        "Char",
        3,
        "text",
        "availability_code",
        "Patient Survival data availability code",
        "patient_survival_data_availability_code",
        outcome_family="survival",
        outcome_role="availability",
    ),
    _required(
        "survival_category",
        "DFCMORTTEXT",
        "Patient Survival Category Text",
        "Patient survival category: better, worse, or as expected.",
        "Char",
        20,
        "text",
        "category",
        "Patient Survival Category Text",
        "patient_survival_category_text",
        availability_companion="survival_availability",
        outcome_family="survival",
        outcome_role="category",
    ),
    _required(
        "survival_denominator",
        "RDSMZ_F",
        "Number Of Patients Included In Survival Summary",
        "The number of patients included in the facility survival summary.",
        "Num",
        8,
        "numeric",
        "patients",
        "Number of Patients included in survival summary",
        "number_of_patients_included_in_survival_summary",
        availability_companion="survival_availability",
        outcome_family="survival",
        outcome_role="denominator",
    ),
    _required(
        "survival_estimate",
        "SMR_RATE_F",
        "Mortality Rate (FACILITY)",
        "The facility mortality rate per 100 patient-years.",
        "Num",
        8,
        "numeric",
        "rate_per_100_patient_years",
        "Mortality Rate (Facility)",
        "mortality_rate_facility",
        availability_companion="survival_availability",
        outcome_family="survival",
        outcome_role="estimate",
    ),
    _required(
        "survival_lower_confidence_limit",
        "SMR_RATE_LCI_F",
        "Mortality Rate: Lower Confidence Limit (2.5%)",
        "The 2.5% lower confidence limit for the mortality rate.",
        "Num",
        8,
        "numeric",
        "rate_per_100_patient_years",
        "Mortality Rate: Lower Confidence Limit (2.5%)",
        "mortality_rate_lower_confidence_limit_25",
        availability_companion="survival_availability",
        outcome_family="survival",
        outcome_role="lower_confidence_limit",
    ),
    _required(
        "survival_upper_confidence_limit",
        "SMR_RATE_UCI_F",
        "Mortality Rate: Upper Confidence Limit (97.5%)",
        "The 97.5% upper confidence limit for the mortality rate.",
        "Num",
        8,
        "numeric",
        "rate_per_100_patient_years",
        "Mortality Rate: Upper Confidence Limit (97.5%)",
        "mortality_rate_upper_confidence_limit_975",
        availability_companion="survival_availability",
        outcome_family="survival",
        outcome_role="upper_confidence_limit",
    ),
    _required(
        "hospitalization_period",
        "DATE_SHR",
        "SHR Date",
        "The period for the patient hospitalization summary.",
        "Char",
        19,
        "text",
        "period",
        "SHR Date",
        "shr_date",
        availability_companion="hospitalization_availability",
        outcome_family="hospitalization",
        outcome_role="period",
    ),
    _required(
        "hospitalization_availability",
        "PTHOSP_C",
        "Patient Hospitalization Data Availability Code",
        "Whether hospitalization data are available or why they are unavailable.",
        "Char",
        3,
        "text",
        "availability_code",
        "Patient Hospitalization data availability Code",
        "patient_hospitalization_data_availability_code",
        outcome_family="hospitalization",
        outcome_role="availability",
    ),
    _required(
        "hospitalization_category",
        "DFCHOSPTEXT",
        "Patient Hospitalization Category Text",
        "Patient hospitalization category: better, worse, or as expected.",
        "Char",
        20,
        "text",
        "category",
        "Patient hospitalization category text",
        "patient_hospitalization_category_text",
        availability_companion="hospitalization_availability",
        outcome_family="hospitalization",
        outcome_role="category",
    ),
    _required(
        "hospitalization_denominator",
        "RDSHY4_F",
        "Number Of Patients Included In Hospitalization Summary",
        "The number of patients included in the facility hospitalization summary.",
        "Num",
        8,
        "numeric",
        "patients",
        "Number of patients included in hospitalization summary",
        "number_of_patients_included_in_hospitalization_summary",
        availability_companion="hospitalization_availability",
        outcome_family="hospitalization",
        outcome_role="denominator",
    ),
    _required(
        "hospitalization_estimate",
        "SHR_RATE_F",
        "Hospitalization Rate (FACILITY)",
        "The facility hospitalization rate per 100 patient-years.",
        "Num",
        8,
        "numeric",
        "rate_per_100_patient_years",
        "Hospitalization Rate (Facility)",
        "hospitalization_rate_facility",
        availability_companion="hospitalization_availability",
        outcome_family="hospitalization",
        outcome_role="estimate",
    ),
    _required(
        "hospitalization_lower_confidence_limit",
        "SHR_RATE_LCI_F",
        "Hospitalization Rate: Lower Confidence Limit (2.5%)",
        "The 2.5% lower confidence limit for the hospitalization rate.",
        "Num",
        8,
        "numeric",
        "rate_per_100_patient_years",
        "Hospitalization Rate: Lower Confidence Limit (2.5%)",
        "hospitalization_rate_lower_confidence_limit_25",
        availability_companion="hospitalization_availability",
        outcome_family="hospitalization",
        outcome_role="lower_confidence_limit",
    ),
    _required(
        "hospitalization_upper_confidence_limit",
        "SHR_RATE_UCI_F",
        "Hospitalization Rate: Upper Confidence Limit (97.5%)",
        "The 97.5% upper confidence limit for the hospitalization rate.",
        "Num",
        8,
        "numeric",
        "rate_per_100_patient_years",
        "Hospitalization Rate: Upper Confidence Limit (97.5%)",
        "hospitalization_rate_upper_confidence_limit_975",
        availability_companion="hospitalization_availability",
        outcome_family="hospitalization",
        outcome_role="upper_confidence_limit",
    ),
    _required(
        "readmission_period",
        "DATE_SRR",
        "SRR Date",
        "The period for the patient readmission summary.",
        "Char",
        19,
        "text",
        "period",
        "SRR Date",
        "srr_date",
        availability_companion="readmission_availability",
        outcome_family="readmission",
        outcome_role="period",
    ),
    _required(
        "readmission_availability",
        "PTREAD_C",
        "Patient Hospital Readmission Data Availability Code",
        "Whether readmission data are available or why they are unavailable.",
        "Char",
        3,
        "text",
        "availability_code",
        "Patient Hospital Readmission data availability Code",
        "patient_hospital_readmission_data_availability_code",
        outcome_family="readmission",
        outcome_role="availability",
    ),
    _required(
        "readmission_category",
        "DFCSRRTEXT",
        "Patient Hospital Readmission Category Text",
        "Patient readmission category: better, worse, or as expected.",
        "Char",
        20,
        "text",
        "category",
        "Patient Hospital Readmission Category",
        "patient_hospital_readmission_category",
        availability_companion="readmission_availability",
        outcome_family="readmission",
        outcome_role="category",
    ),
    _required(
        "readmission_denominator",
        "INDEXY4_f",
        "Number Of Hospitalizations Included In Hospital Readmission Summary",
        "The number of index discharges in the facility readmission summary.",
        "Num",
        8,
        "numeric",
        "index_discharges",
        "Number of hospitalizations included in hospital readmission summary",
        "number_of_hospitalizations_included_in_hospital_readmission_fc2b",
        availability_companion="readmission_availability",
        outcome_family="readmission",
        outcome_role="denominator",
    ),
    _required(
        "readmission_estimate",
        "SRR_RATE_F",
        "Readmission Rate (FACILITY)",
        "The facility readmission rate as a percent of hospital discharges.",
        "Num",
        8,
        "numeric",
        "percent_of_hospital_discharges",
        "Readmission Rate (Facility)",
        "readmission_rate_facility",
        availability_companion="readmission_availability",
        outcome_family="readmission",
        outcome_role="estimate",
    ),
    _required(
        "readmission_lower_confidence_limit",
        "SRR_RATE_LCI_F",
        "Readmission Rate: Lower Confidence Limit (2.5%)",
        "The 2.5% lower confidence limit for the readmission rate.",
        "Num",
        8,
        "numeric",
        "percent_of_hospital_discharges",
        "Readmission Rate: Lower Confidence Limit (2.5%)",
        "readmission_rate_lower_confidence_limit_25",
        availability_companion="readmission_availability",
        outcome_family="readmission",
        outcome_role="lower_confidence_limit",
    ),
    _required(
        "readmission_upper_confidence_limit",
        "SRR_RATE_UCI_F",
        "Readmission Rate: Upper Confidence Limit (97.5%)",
        "The 97.5% upper confidence limit for the readmission rate.",
        "Num",
        8,
        "numeric",
        "percent_of_hospital_discharges",
        "Readmission Rate: Upper Confidence Limit (97.5%)",
        "readmission_rate_upper_confidence_limit_975",
        availability_companion="readmission_availability",
        outcome_family="readmission",
        outcome_role="upper_confidence_limit",
    ),
)

_EXPECTED_BY_SEMANTIC: Final = MappingProxyType(
    {field.semantic: field for field in REQUIRED_FIELDS}
)
OUTCOME_FAMILIES: Final = MappingProxyType(
    {
        family: tuple(
            field for field in REQUIRED_FIELDS if field.outcome_family == family
        )
        for family in ("survival", "hospitalization", "readmission")
    }
)
_TYPE_FAMILY: Final = MappingProxyType(
    {
        "CHAR": "text",
        "TEXT": "text",
        "INT": "integer",
        "INTEGER": "integer",
        "NUM": "numeric",
        "NUMERIC": "numeric",
        "DATETIME": "date",
        "DATE": "date",
    }
)


def _duplicates(values: Iterable[str]) -> tuple[str, ...]:
    counts = Counter(values)
    return tuple(sorted(value for value, count in counts.items() if count > 1))


def validate_required_mapping(
    fields: Iterable[RequiredField],
) -> ValidationResult:
    """Validate the exact bounded cross-surface semantic mapping."""
    observed = tuple(fields)
    by_semantic = {field.semantic: field for field in observed}
    issues: list[ValidationIssue] = []

    for semantic in _EXPECTED_BY_SEMANTIC:
        if semantic not in by_semantic:
            issues.append(
                ValidationIssue(
                    code="missing_required_mapping",
                    field=semantic,
                    message=f"Required semantic mapping is missing: {semantic}",
                )
            )
    duplicate_semantics = _duplicates(field.semantic for field in observed)
    for semantic in duplicate_semantics:
        issues.append(
            ValidationIssue(
                code="duplicate_semantic_mapping",
                field=semantic,
                message=f"Semantic concept appears more than once: {semantic}",
            )
        )

    duplicate_csv = _duplicates(field.csv_header for field in observed)
    duplicate_api = _duplicates(field.api_field_name for field in observed)
    if duplicate_csv or duplicate_api:
        issues.extend(
            ValidationIssue(
                code="duplicate_csv_mapping_target",
                field=header,
                message=f"CSV mapping target appears more than once: {header}",
            )
            for header in duplicate_csv
        )
        issues.extend(
            ValidationIssue(
                code="duplicate_api_mapping_target",
                field=api_name,
                message=f"API mapping target appears more than once: {api_name}",
            )
            for api_name in duplicate_api
        )
        return ValidationResult(issues=tuple(issues))

    for semantic, expected in _EXPECTED_BY_SEMANTIC.items():
        actual = by_semantic.get(semantic)
        if actual is None:
            continue
        if actual.dictionary_variable != expected.dictionary_variable:
            issues.append(
                ValidationIssue(
                    code="incompatible_dictionary_mapping",
                    field=semantic,
                    message=(
                        f"Required semantic {semantic} maps to dictionary variable "
                        f"{actual.dictionary_variable!r}; expected "
                        f"{expected.dictionary_variable!r}"
                    ),
                )
            )
        for attribute, code, label in (
            (
                "dictionary_label",
                "incompatible_dictionary_label",
                "dictionary label",
            ),
            (
                "dictionary_definition",
                "incompatible_dictionary_definition",
                "dictionary definition",
            ),
            (
                "maximum_length",
                "incompatible_dictionary_maximum_length",
                "dictionary maximum length",
            ),
            ("unit", "incompatible_dictionary_unit", "dictionary unit"),
            (
                "availability_companion",
                "incompatible_availability_companion",
                "availability companion",
            ),
            ("outcome_family", "incompatible_outcome_family", "outcome family"),
            ("outcome_role", "incompatible_outcome_role", "outcome role"),
        ):
            actual_value = getattr(actual, attribute)
            expected_value = getattr(expected, attribute)
            if actual_value != expected_value:
                issues.append(
                    ValidationIssue(
                        code=code,
                        field=semantic,
                        message=(
                            f"Required semantic {semantic} has {label} "
                            f"{actual_value!r}; expected {expected_value!r}"
                        ),
                    )
                )
        if actual.csv_header != expected.csv_header:
            issues.append(
                ValidationIssue(
                    code="incompatible_csv_mapping",
                    field=semantic,
                    message=(
                        f"Required semantic {semantic} maps to CSV header "
                        f"{actual.csv_header!r}; expected {expected.csv_header!r}"
                    ),
                )
            )
        if actual.api_field_name != expected.api_field_name:
            issues.append(
                ValidationIssue(
                    code="incompatible_api_mapping",
                    field=semantic,
                    message=(
                        f"Required semantic {semantic} maps to API field "
                        f"{actual.api_field_name!r}; expected "
                        f"{expected.api_field_name!r}"
                    ),
                )
            )
        actual_family = _TYPE_FAMILY.get(actual.dictionary_declared_type.upper())
        if actual_family != expected.type_family:
            issues.append(
                ValidationIssue(
                    code="incompatible_dictionary_type",
                    field=semantic,
                    message=(
                        f"Required semantic {semantic} has dictionary type "
                        f"{actual.dictionary_declared_type!r}; expected "
                        f"{expected.type_family} family"
                    ),
                )
            )
        if actual.type_family != expected.type_family:
            issues.append(
                ValidationIssue(
                    code="incompatible_contract_type_family",
                    field=semantic,
                    message=(
                        f"Required semantic {semantic} has normalized type family "
                        f"{actual.type_family!r}; expected {expected.type_family!r}"
                    ),
                )
            )
    return ValidationResult(issues=tuple(issues))


def validate_api_schema(fields: Iterable[ApiField]) -> ValidationResult:
    """Validate ordered Provider Data API fields against required mappings."""
    observed = tuple(fields)
    api_counts = Counter(field.api_field_name for field in observed)
    csv_counts = Counter(field.csv_header for field in observed)
    first_by_api: dict[str, ApiField] = {}
    for field in observed:
        first_by_api.setdefault(field.api_field_name, field)

    issues: list[ValidationIssue] = []
    required_csv_headers = {field.csv_header for field in REQUIRED_FIELDS}
    for header in _duplicates(field.csv_header for field in observed):
        if header not in required_csv_headers:
            issues.append(
                ValidationIssue(
                    code="duplicate_additive_csv_header",
                    field=header,
                    message=(
                        "Compatible additive CSV header appears more than once: "
                        f"{header}"
                    ),
                )
            )
    for required in REQUIRED_FIELDS:
        count = api_counts[required.api_field_name]
        if count == 0:
            issues.append(
                ValidationIssue(
                    code="missing_required_api_field",
                    field=required.semantic,
                    message=(
                        f"Required API field is missing for {required.semantic}: "
                        f"{required.api_field_name}"
                    ),
                )
            )
            continue
        if count > 1:
            issues.append(
                ValidationIssue(
                    code="duplicate_required_api_field",
                    field=required.semantic,
                    message=(
                        f"Required API field appears more than once for "
                        f"{required.semantic}: {required.api_field_name}"
                    ),
                )
            )
            continue
        actual = first_by_api[required.api_field_name]
        if actual.csv_header != required.csv_header:
            issues.append(
                ValidationIssue(
                    code="incompatible_api_csv_mapping",
                    field=required.semantic,
                    message=(
                        f"API field {required.api_field_name} describes CSV header "
                        f"{actual.csv_header!r}; expected {required.csv_header!r}"
                    ),
                )
            )
        if actual.declared_type.strip().casefold() != "text":
            issues.append(
                ValidationIssue(
                    code="incompatible_api_transport_type",
                    field=required.semantic,
                    message=(
                        f"API field {required.api_field_name} has transport type "
                        f"{actual.declared_type!r}; expected raw text"
                    ),
                )
            )
        if csv_counts[required.csv_header] != 1:
            issues.append(
                ValidationIssue(
                    code="ambiguous_required_csv_header",
                    field=required.semantic,
                    message=(
                        f"Required CSV header must map exactly once: "
                        f"{required.csv_header}"
                    ),
                )
            )

    required_api = {field.api_field_name for field in REQUIRED_FIELDS}
    additive = tuple(
        sorted(
            field.csv_header
            for field in observed
            if field.api_field_name not in required_api
        )
    )
    return ValidationResult(issues=tuple(issues), additive_fields=additive)


def validate_facility_rows(
    rows: Iterable[Mapping[str, object]],
) -> ValidationResult:
    """Validate nonblank, textual, unique CCNs without filtering source rows."""
    issues: list[ValidationIssue] = []
    first_row_by_ccn: dict[str, int] = {}
    for source_row_number, row in enumerate(rows, start=2):
        if CCN_CSV_HEADER not in row:
            issues.append(
                ValidationIssue(
                    code="missing_ccn",
                    field=CCN_CSV_HEADER,
                    message=f"Source row {source_row_number} is missing CCN",
                )
            )
            continue
        ccn = row[CCN_CSV_HEADER]
        if not isinstance(ccn, str) or not ccn.strip():
            issues.append(
                ValidationIssue(
                    code="blank_ccn",
                    field=CCN_CSV_HEADER,
                    message=f"CCN is blank at source row {source_row_number}",
                )
            )
            continue
        if _CCN_PATTERN.fullmatch(ccn) is None:
            issues.append(
                ValidationIssue(
                    code="invalid_ccn_format",
                    field=CCN_CSV_HEADER,
                    message=(
                        "CCN must be 1-10 ASCII-digit text at source row "
                        f"{source_row_number}: {ccn!r}"
                    ),
                )
            )
            continue
        first_row = first_row_by_ccn.setdefault(ccn, source_row_number)
        if first_row != source_row_number:
            issues.append(
                ValidationIssue(
                    code="duplicate_ccn",
                    field=CCN_CSV_HEADER,
                    message=(
                        f"Duplicate CCN {ccn!r} at source row {source_row_number}; "
                        f"first seen at row {first_row}"
                    ),
                )
            )
    return ValidationResult(
        issues=tuple(issues),
        distinct_ccn_count=len(first_row_by_ccn),
    )
