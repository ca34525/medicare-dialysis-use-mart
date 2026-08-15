select *
from {{ ref('dim_county') }}
where not regexp_full_match(county_fips, '[0-9]{5}')
   or not regexp_full_match(state_fips, '[0-9]{2}')
   or substr(county_fips, 1, 2) <> state_fips
   or state_fips in ('60', '66', '69', '72', '78')
   or (state_fips = '11' and county_fips <> '11001')
   or geography_status not in ('current_in_scope', 'historical_source_only')
   or (
       is_current_county
       and (
           geography_status <> 'current_in_scope'
           or svi_geography_vintage <> 2022
           or boundary_discontinuity_warning is not null
           or geography_source_id <> 'cdc_svi_county_2022'
           or geography_source_version <> 'cdc_svi_county_2022.raw.v1'
           or not regexp_full_match(
               geography_source_snapshot_sha256,
               '[0-9a-f]{64}'
           )
       )
   )
   or (
       not is_current_county
       and (
           geography_status <> 'historical_source_only'
           or svi_geography_vintage is not null
           or observed_cms_start_year is null
           or observed_cms_end_year is null
           or observed_cms_start_year > observed_cms_end_year
           or boundary_discontinuity_warning is null
           or geography_source_id <> 'cms_om_gv_historical_identity_seed'
           or geography_source_version <> 'plan006.1'
           or geography_source_manifest_run_id <> 'version-controlled-seed'
           or geography_source_snapshot_sha256 is not null
       )
   )
