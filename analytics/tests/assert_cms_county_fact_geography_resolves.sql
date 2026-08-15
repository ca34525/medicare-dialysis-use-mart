select fact.county_fips, fact.year
from {{ ref('fct_medicare_county_year') }} as fact
left join {{ ref('dim_county') }} as county using (county_fips)
where county.county_fips is null
