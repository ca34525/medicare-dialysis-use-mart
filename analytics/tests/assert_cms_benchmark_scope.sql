select *
from {{ ref('stg_cms_om_gv_benchmark_year') }}
where source_age_level <> 'All'
   or benchmark_geography_type not in ('state', 'national')
   or (
       benchmark_geography_type = 'state'
       and not regexp_full_match(benchmark_geography_key, '[0-9]{2}')
   )
   or (
       benchmark_geography_type = 'national'
       and (
           benchmark_geography_key <> 'US'
           or coalesce(source_geography_code, '') <> ''
       )
   )
