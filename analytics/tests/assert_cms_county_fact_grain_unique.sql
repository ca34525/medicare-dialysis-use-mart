select county_fips, year, count(*) as row_count
from {{ ref('fct_medicare_county_year') }}
group by county_fips, year
having count(*) <> 1
