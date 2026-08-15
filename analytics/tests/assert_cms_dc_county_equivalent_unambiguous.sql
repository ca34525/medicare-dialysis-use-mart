select year, count(*) as candidate_count
from {{ ref('stg_cms_om_gv_county_year') }}
where county_fips = '11001'
group by year
having count(*) > 1
   and bool_or(
       county_geography_mapping_method =
       'district_of_columbia_state_to_county_equivalent'
   )
   and bool_or(county_geography_mapping_method = 'source_county_fips')
