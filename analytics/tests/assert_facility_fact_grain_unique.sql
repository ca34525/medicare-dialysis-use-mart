select ccn, source_snapshot_sha256, count(*) as row_count
from {{ ref('fct_facility_quality_snapshot') }}
group by ccn, source_snapshot_sha256
having count(*) != 1
