{{ config(contract={"enforced": true}) }}

with cms_observation_years as (
    select
        county_fips,
        min(year) as observed_cms_start_year,
        max(year) as observed_cms_end_year
    from {{ ref('stg_cms_om_gv_county_year') }}
    group by county_fips
),

current_counties as (
    select
        svi.county_fips,
        svi.state_fips,
        svi.state_name,
        svi.state_abbreviation,
        svi.county_name,
        'current_in_scope' as geography_status,
        true as is_current_county,
        svi.svi_vintage as svi_geography_vintage,
        cms.observed_cms_start_year,
        cms.observed_cms_end_year,
        cast(null as varchar) as boundary_discontinuity_warning,
        svi.source_id as geography_source_id,
        'cdc_svi_county_2022.raw.v1' as geography_source_version,
        svi.source_manifest_run_id as geography_source_manifest_run_id,
        svi.source_snapshot_sha256 as geography_source_snapshot_sha256
    from {{ ref('stg_cdc_svi_county_2022') }} as svi
    left join cms_observation_years as cms using (county_fips)
),

historical_counties as (
    select
        county_fips,
        state_fips,
        state_name,
        state_abbreviation,
        county_name,
        geography_status,
        cast(is_current_county as boolean) as is_current_county,
        cast(null as integer) as svi_geography_vintage,
        observed_cms_start_year,
        observed_cms_end_year,
        boundary_discontinuity_warning,
        'cms_om_gv_historical_identity_seed' as geography_source_id,
        seed_version as geography_source_version,
        'version-controlled-seed' as geography_source_manifest_run_id,
        cast(null as varchar) as geography_source_snapshot_sha256
    from {{ ref('historical_county_identities') }}
)

select * from current_counties
union all by name
select * from historical_counties
