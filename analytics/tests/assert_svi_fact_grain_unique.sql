select county_fips, svi_vintage, count(*) as row_count
from {{ ref('fct_svi_county') }}
group by county_fips, svi_vintage
having count(*) <> 1
