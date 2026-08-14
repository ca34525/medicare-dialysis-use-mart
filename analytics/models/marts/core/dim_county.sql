{{ config(contract={"enforced": true}) }}

select
    county_fips,
    state_fips,
    state_name,
    state_abbreviation,
    county_name,
    'valid_in_scope' as geography_status,
    svi_vintage as svi_geography_vintage,
    source_id as geography_source_id,
    source_manifest_run_id as geography_source_manifest_run_id,
    source_snapshot_sha256 as geography_source_snapshot_sha256
from {{ ref('stg_cdc_svi_county_2022') }}
