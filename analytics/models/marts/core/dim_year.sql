{{ config(contract={"enforced": true}) }}

with observed_years as (
    select year from {{ ref('stg_cms_om_gv_county_year') }}
    union
    select year from {{ ref('stg_cms_om_gv_benchmark_year') }}
)

select
    year,
    year = max(year) over () as is_latest_cms_year
from observed_years
