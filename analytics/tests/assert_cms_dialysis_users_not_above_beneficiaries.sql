with facts as (
    select 'county' as fact_type, county_fips as geography_key, year,
           benes_om_cnt, benes_op_dlys_cnt
    from {{ ref('fct_medicare_county_year') }}
    union all
    select benchmark_geography_type, benchmark_geography_key, year,
           benes_om_cnt, benes_op_dlys_cnt
    from {{ ref('fct_medicare_benchmark_year') }}
)

select *
from facts
where benes_om_cnt is not null
  and benes_op_dlys_cnt is not null
  and benes_op_dlys_cnt > benes_om_cnt
