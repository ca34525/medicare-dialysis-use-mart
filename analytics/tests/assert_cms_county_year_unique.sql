select county_fips, year, count(*) as row_count
from {{ ref('stg_cms_om_gv_county_year') }}
group by county_fips, year
having count(*) <> 1
