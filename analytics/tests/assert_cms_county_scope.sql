select *
from {{ ref('stg_cms_om_gv_county_year') }}
where source_geography_level <> 'County'
   or source_age_level <> 'All'
   or substr(county_fips, 1, 2) in ('60', '66', '69', '72', '78')
   or (
       regexp_full_match(trim(source_geography_code), '[0-9]{2}000')
       and regexp_full_match(
           upper(trim(source_geography_description)),
           '[A-Z]{2}-UNKNOWN'
       )
   )
