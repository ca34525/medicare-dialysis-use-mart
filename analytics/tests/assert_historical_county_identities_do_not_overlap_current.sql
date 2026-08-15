select historical.county_fips
from {{ ref('historical_county_identities') }} as historical
inner join {{ ref('stg_cdc_svi_county_2022') }} as current
    using (county_fips)
