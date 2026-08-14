select *
from {{ ref('dim_county') }}
where not regexp_full_match(county_fips, '[0-9]{5}')
   or not regexp_full_match(state_fips, '[0-9]{2}')
   or substr(county_fips, 1, 2) <> state_fips
   or state_fips in ('60', '66', '69', '72', '78')
   or (state_fips = '11' and county_fips <> '11001')
   or geography_status <> 'valid_in_scope'
   or svi_geography_vintage <> 2022
   or geography_source_id <> 'cdc_svi_county_2022'
   or not regexp_full_match(geography_source_snapshot_sha256, '[0-9a-f]{64}')
