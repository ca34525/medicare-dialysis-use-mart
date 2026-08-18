{{ config(contract={"enforced": true}) }}

select
    ccn,
    facility_name,
    address_line_1,
    address_line_2,
    city,
    state,
    zip_code,
    source_county,
    telephone,
    ownership_status,
    chain_owned,
    chain_organization,
    dialysis_stations,
    in_center_hemodialysis,
    peritoneal_dialysis,
    home_hemodialysis_training,
    certification_date,
    cast(null as varchar) as county_fips,
    'not_attempted'::varchar as geography_match_status,
    cast(null as varchar) as geography_match_method,
    cast(null as date) as geography_resolution_date,
    'facility geography assignment is deferred'::varchar
        as geography_provenance,
    source_id,
    source_manifest_run_id,
    source_snapshot_sha256,
    source_retrieved_at_utc,
    source_release,
    source_modified_at
from {{ ref('stg_cms_dialysis_facility') }}
