select *
from {{ ref('stg_cdc_svi_county_2022') }}
where not regexp_full_match(county_fips, '[0-9]{5}')
   or not regexp_full_match(state_fips, '[0-9]{2}')
   or substr(county_fips, 1, 2) <> state_fips
   or state_fips in ('60', '66', '69', '72', '78')
   or (state_fips = '11' and county_fips <> '11001')
   or coalesce(trim(state_name), '') = ''
   or coalesce(trim(state_abbreviation), '') = ''
   or coalesce(trim(county_name), '') = ''
   or source_object_id <= 0
