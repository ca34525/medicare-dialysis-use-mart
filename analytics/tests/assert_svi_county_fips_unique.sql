select county_fips, count(*) as row_count
from {{ ref('stg_cdc_svi_county_2022') }}
group by county_fips
having count(*) <> 1
