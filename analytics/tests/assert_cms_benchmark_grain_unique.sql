select benchmark_geography_type, benchmark_geography_key, year, count(*)
from {{ ref('stg_cms_om_gv_benchmark_year') }}
group by benchmark_geography_type, benchmark_geography_key, year
having count(*) <> 1
