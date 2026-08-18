select ccn
from {{ ref('dim_facility') }}
where county_fips is not null
   or geography_match_status != 'not_attempted'
   or geography_match_method is not null
   or geography_resolution_date is not null
