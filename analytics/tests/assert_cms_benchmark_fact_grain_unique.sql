select
    benchmark_geography_type,
    benchmark_geography_key,
    year,
    count(*) as row_count
from {{ ref('fct_medicare_benchmark_year') }}
group by benchmark_geography_type, benchmark_geography_key, year
having count(*) <> 1
