with observed as (
    select year from {{ ref('fct_medicare_county_year') }}
    union
    select year from {{ ref('fct_medicare_benchmark_year') }}
),

dimension_years as (
    select year from {{ ref('dim_year') }}
),

differences as (
    (select * from observed except select * from dimension_years)
    union all
    (select * from dimension_years except select * from observed)
)

select * from differences
