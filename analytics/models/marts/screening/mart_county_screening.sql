{{ config(materialized="table", contract={"enforced": true}) }}

with threshold as (
    select * from {{ ref('int_county_screening_threshold') }}
),

current_counties as (
    select *
    from {{ ref('dim_county') }}
    where is_current_county
),

latest_medicare as (
    select fact.*
    from {{ ref('fct_medicare_county_year') }} as fact
    cross join threshold
    where fact.year = threshold.cms_year
),

current_svi as (
    select svi.*
    from {{ ref('fct_svi_county') }} as svi
    cross join threshold
    where svi.svi_vintage = threshold.svi_vintage
),

joined as (
    select
        threshold.screening_definition_version,
        threshold.screening_run_id,
        threshold.input_set_sha256,
        county.county_fips,
        county.state_fips,
        county.state_name,
        county.state_abbreviation,
        county.county_name,
        county.geography_status,
        county.boundary_discontinuity_warning,
        reconciliation.reconciliation_status,
        reconciliation.cms_row_count as cms_reconciliation_row_count,
        reconciliation.svi_row_count as svi_reconciliation_row_count,
        threshold.cms_year,
        threshold.svi_vintage,
        svi.acs_period_start,
        svi.acs_period_end,
        medicare.benes_om_cnt,
        medicare.benes_om_cnt_status,
        medicare.benes_op_dlys_pct,
        medicare.benes_op_dlys_pct_status,
        threshold.dialysis_use_p75_threshold,
        threshold.threshold_eligible_count,
        svi.rpl_themes,
        svi.rpl_themes_status,
        medicare.source_manifest_run_id as cms_source_manifest_run_id,
        medicare.source_content_sha256 as cms_source_content_sha256,
        medicare.source_retrieved_at_utc as cms_source_retrieved_at_utc,
        medicare.source_modified_at as cms_source_modified_at,
        svi.source_manifest_run_id as svi_source_manifest_run_id,
        svi.source_snapshot_sha256 as svi_source_snapshot_sha256,
        svi.source_retrieved_at_utc as svi_source_retrieved_at_utc,
        svi.source_modified_at as svi_source_modified_at
    from current_counties as county
    cross join threshold
    left join latest_medicare as medicare using (county_fips)
    left join current_svi as svi using (county_fips)
    left join {{ ref('audit_cms_svi_county_reconciliation') }} as reconciliation
        using (county_fips)
),

availability as (
    select
        *,
        benes_op_dlys_pct_status = 'reported'
            and benes_op_dlys_pct is not null
            as is_dialysis_use_threshold_eligible,
        rpl_themes_status = 'reported'
            and rpl_themes is not null
            as is_social_vulnerability_available
    from joined
),

component_flags as (
    select
        *,
        case
            when is_dialysis_use_threshold_eligible
                then benes_op_dlys_pct >= dialysis_use_p75_threshold
            else cast(null as boolean)
        end as is_higher_observed_dialysis_use,
        case
            when not is_dialysis_use_threshold_eligible then 'insufficient_data'
            when benes_op_dlys_pct >= dialysis_use_p75_threshold then 'higher_use'
            else 'lower_use'
        end as dialysis_use_band,
        case
            when is_social_vulnerability_available then rpl_themes >= 0.75
            else cast(null as boolean)
        end as is_higher_social_vulnerability,
        case
            when not is_social_vulnerability_available then 'insufficient_data'
            when rpl_themes >= 0.75 then 'higher_vulnerability'
            else 'lower_vulnerability'
        end as social_vulnerability_band
    from availability
),

classified as (
    select
        *,
        case
            when is_dialysis_use_threshold_eligible
             and is_social_vulnerability_available then 'complete'
            else 'insufficient_data'
        end as screening_data_status,
        case
            when is_dialysis_use_threshold_eligible
             and is_social_vulnerability_available then cast(null as varchar)
            when not is_dialysis_use_threshold_eligible
             and not is_social_vulnerability_available
                then 'both_components_unavailable'
            when not is_dialysis_use_threshold_eligible
                then 'dialysis_use_component_unavailable'
            else 'social_vulnerability_component_unavailable'
        end as screening_insufficient_reason,
        case
            when not is_dialysis_use_threshold_eligible
              or not is_social_vulnerability_available then 'insufficient_data'
            when is_higher_observed_dialysis_use
             and is_higher_social_vulnerability
                then 'higher_use_higher_vulnerability'
            when is_higher_observed_dialysis_use
                then 'higher_use_lower_vulnerability'
            when is_higher_social_vulnerability
                then 'lower_use_higher_vulnerability'
            else 'lower_use_lower_vulnerability'
        end as screening_quadrant
    from component_flags
)

select
    screening_definition_version,
    screening_run_id,
    input_set_sha256,
    county_fips,
    state_fips,
    state_name,
    state_abbreviation,
    county_name,
    geography_status,
    boundary_discontinuity_warning,
    reconciliation_status,
    cms_reconciliation_row_count,
    svi_reconciliation_row_count,
    cms_year,
    svi_vintage,
    acs_period_start,
    acs_period_end,
    benes_om_cnt,
    benes_om_cnt_status,
    benes_op_dlys_pct,
    benes_op_dlys_pct_status,
    dialysis_use_p75_threshold,
    threshold_eligible_count,
    is_dialysis_use_threshold_eligible,
    is_higher_observed_dialysis_use,
    dialysis_use_band,
    rpl_themes,
    rpl_themes_status,
    is_higher_social_vulnerability,
    social_vulnerability_band,
    screening_data_status,
    screening_insufficient_reason,
    screening_quadrant,
    cms_source_manifest_run_id,
    cms_source_content_sha256,
    cms_source_retrieved_at_utc,
    cms_source_modified_at,
    svi_source_manifest_run_id,
    svi_source_snapshot_sha256,
    svi_source_retrieved_at_utc,
    svi_source_modified_at
from classified
