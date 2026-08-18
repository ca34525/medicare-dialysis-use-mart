{{ config(contract={"enforced": true}) }}

with raw_source as (
    select *
    from {{ source('raw', 'cms_dialysis_facility') }}
),

renamed as (
    select
        "CMS Certification Number (CCN)" as ccn,
        "Facility Name" as facility_name,
        "Address Line 1" as address_line_1,
        "Address Line 2" as address_line_2,
        "City/Town" as city,
        "State" as state,
        "ZIP Code" as zip_code,
        "County/Parish" as source_county,
        "Telephone Number" as telephone,
        "Profit or Non-Profit" as ownership_status,
        "Chain Owned" as chain_owned_raw,
        case lower(trim("Chain Owned"))
            when 'yes' then true
            when 'no' then false
        end as chain_owned,
        "Chain Organization" as chain_organization,
        "# of Dialysis Stations" as dialysis_stations_raw,
        try_cast(nullif(trim("# of Dialysis Stations"), '') as integer)
            as dialysis_stations,
        "Offers in-center hemodialysis" as in_center_hemodialysis_raw,
        case lower(trim("Offers in-center hemodialysis"))
            when 'yes' then true
            when 'no' then false
        end as in_center_hemodialysis,
        "Offers peritoneal dialysis" as peritoneal_dialysis_raw,
        case lower(trim("Offers peritoneal dialysis"))
            when 'yes' then true
            when 'no' then false
        end as peritoneal_dialysis,
        "Offers home hemodialysis training" as home_hemodialysis_training_raw,
        case lower(trim("Offers home hemodialysis training"))
            when 'yes' then true
            when 'no' then false
        end as home_hemodialysis_training,
        "Certification Date" as certification_date_raw,
        try_cast(nullif(trim("Certification Date"), '') as date)
            as certification_date,

        "Five Star Date" as five_star_period_raw,
        {{ facility_period_start('"Five Star Date"') }} as five_star_period_start,
        {{ facility_period_end('"Five Star Date"') }} as five_star_period_end,
        "Five Star" as five_star_rating_raw,
        case when trim("Five Star Data Availability Code") = '001'
            then try_cast(nullif(trim("Five Star"), '') as integer)
        end as five_star_rating,
        "Five Star Data Availability Code" as five_star_availability_code,
        {{ facility_availability_status('"Five Star Data Availability Code"', 'star') }}
            as five_star_availability_status,
        {{ facility_unavailability_reason('"Five Star Data Availability Code"') }}
            as five_star_unavailability_reason,

        "SMR Date" as survival_period_raw,
        {{ facility_period_start('"SMR Date"') }} as survival_period_start,
        {{ facility_period_end('"SMR Date"') }} as survival_period_end,
        "Patient Survival data availability code" as survival_availability_code,
        {{ facility_availability_status('"Patient Survival data availability code"', 'outcome') }}
            as survival_availability_status,
        {{ facility_unavailability_reason('"Patient Survival data availability code"') }}
            as survival_unavailability_reason,
        "Patient Survival Category Text" as survival_category_raw,
        case when trim("Patient Survival data availability code") = '001' then
            case lower(trim("Patient Survival Category Text"))
                when 'better than expected' then 'better_than_expected'
                when 'as expected' then 'as_expected'
                when 'worse than expected' then 'worse_than_expected'
            end
        end as survival_category,
        "Number of Patients included in survival summary" as survival_denominator_raw,
        case when trim("Patient Survival data availability code") = '001'
            then try_cast(nullif(trim("Number of Patients included in survival summary"), '') as bigint)
        end as survival_denominator,
        "Mortality Rate (Facility)" as survival_estimate_raw,
        case when trim("Patient Survival data availability code") = '001'
            then try_cast(nullif(trim("Mortality Rate (Facility)"), '') as decimal(18, 10))
        end as survival_estimate,
        "Mortality Rate: Lower Confidence Limit (2.5%)"
            as survival_lower_confidence_limit_raw,
        case when trim("Patient Survival data availability code") = '001'
            then try_cast(nullif(trim("Mortality Rate: Lower Confidence Limit (2.5%)"), '') as decimal(18, 10))
        end as survival_lower_confidence_limit,
        "Mortality Rate: Upper Confidence Limit (97.5%)"
            as survival_upper_confidence_limit_raw,
        case when trim("Patient Survival data availability code") = '001'
            then try_cast(nullif(trim("Mortality Rate: Upper Confidence Limit (97.5%)"), '') as decimal(18, 10))
        end as survival_upper_confidence_limit,

        "SHR Date" as hospitalization_period_raw,
        {{ facility_period_start('"SHR Date"') }} as hospitalization_period_start,
        {{ facility_period_end('"SHR Date"') }} as hospitalization_period_end,
        "Patient Hospitalization data availability Code"
            as hospitalization_availability_code,
        {{ facility_availability_status('"Patient Hospitalization data availability Code"', 'outcome') }}
            as hospitalization_availability_status,
        {{ facility_unavailability_reason('"Patient Hospitalization data availability Code"') }}
            as hospitalization_unavailability_reason,
        "Patient hospitalization category text" as hospitalization_category_raw,
        case when trim("Patient Hospitalization data availability Code") = '001' then
            case lower(trim("Patient hospitalization category text"))
                when 'better than expected' then 'better_than_expected'
                when 'as expected' then 'as_expected'
                when 'worse than expected' then 'worse_than_expected'
            end
        end as hospitalization_category,
        "Number of patients included in hospitalization summary"
            as hospitalization_denominator_raw,
        case when trim("Patient Hospitalization data availability Code") = '001'
            then try_cast(nullif(trim("Number of patients included in hospitalization summary"), '') as bigint)
        end as hospitalization_denominator,
        "Hospitalization Rate (Facility)" as hospitalization_estimate_raw,
        case when trim("Patient Hospitalization data availability Code") = '001'
            then try_cast(nullif(trim("Hospitalization Rate (Facility)"), '') as decimal(18, 10))
        end as hospitalization_estimate,
        "Hospitalization Rate: Lower Confidence Limit (2.5%)"
            as hospitalization_lower_confidence_limit_raw,
        case when trim("Patient Hospitalization data availability Code") = '001'
            then try_cast(nullif(trim("Hospitalization Rate: Lower Confidence Limit (2.5%)"), '') as decimal(18, 10))
        end as hospitalization_lower_confidence_limit,
        "Hospitalization Rate: Upper Confidence Limit (97.5%)"
            as hospitalization_upper_confidence_limit_raw,
        case when trim("Patient Hospitalization data availability Code") = '001'
            then try_cast(nullif(trim("Hospitalization Rate: Upper Confidence Limit (97.5%)"), '') as decimal(18, 10))
        end as hospitalization_upper_confidence_limit,

        "SRR Date" as readmission_period_raw,
        {{ facility_period_start('"SRR Date"') }} as readmission_period_start,
        {{ facility_period_end('"SRR Date"') }} as readmission_period_end,
        "Patient Hospital Readmission data availability Code"
            as readmission_availability_code,
        {{ facility_availability_status('"Patient Hospital Readmission data availability Code"', 'outcome') }}
            as readmission_availability_status,
        {{ facility_unavailability_reason('"Patient Hospital Readmission data availability Code"') }}
            as readmission_unavailability_reason,
        "Patient Hospital Readmission Category" as readmission_category_raw,
        case when trim("Patient Hospital Readmission data availability Code") = '001' then
            case lower(trim("Patient Hospital Readmission Category"))
                when 'better than expected' then 'better_than_expected'
                when 'as expected' then 'as_expected'
                when 'worse than expected' then 'worse_than_expected'
            end
        end as readmission_category,
        "Number of hospitalizations included in hospital readmission summary"
            as readmission_denominator_raw,
        case when trim("Patient Hospital Readmission data availability Code") = '001'
            then try_cast(nullif(trim("Number of hospitalizations included in hospital readmission summary"), '') as bigint)
        end as readmission_denominator,
        "Readmission Rate (Facility)" as readmission_estimate_raw,
        case when trim("Patient Hospital Readmission data availability Code") = '001'
            then try_cast(nullif(trim("Readmission Rate (Facility)"), '') as decimal(18, 10))
        end as readmission_estimate,
        "Readmission Rate: Lower Confidence Limit (2.5%)"
            as readmission_lower_confidence_limit_raw,
        case when trim("Patient Hospital Readmission data availability Code") = '001'
            then try_cast(nullif(trim("Readmission Rate: Lower Confidence Limit (2.5%)"), '') as decimal(18, 10))
        end as readmission_lower_confidence_limit,
        "Readmission Rate: Upper Confidence Limit (97.5%)"
            as readmission_upper_confidence_limit_raw,
        case when trim("Patient Hospital Readmission data availability Code") = '001'
            then try_cast(nullif(trim("Readmission Rate: Upper Confidence Limit (97.5%)"), '') as decimal(18, 10))
        end as readmission_upper_confidence_limit,

        source_id,
        source_manifest_run_id,
        source_snapshot_sha256,
        source_retrieved_at_utc,
        source_release,
        source_modified_at
    from raw_source
)

select * from renamed
