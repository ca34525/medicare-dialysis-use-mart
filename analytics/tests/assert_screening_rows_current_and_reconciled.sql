select screening.*
from {{ ref('mart_county_screening') }} as screening
left join {{ ref('dim_county') }} as county using (county_fips)
where county.county_fips is null
   or not county.is_current_county
   or screening.geography_status <> 'current_in_scope'
   or screening.reconciliation_status <> 'matched'
   or screening.cms_reconciliation_row_count <> 1
   or screening.svi_reconciliation_row_count <> 1
