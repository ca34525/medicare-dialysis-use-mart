with latest_years as (
    select
        count(*) filter (where is_latest_cms_year) as latest_year_count,
        max(year) filter (where is_latest_cms_year) as latest_year
    from {{ ref('dim_year') }}
),

threshold_years as (
    select
        count(*) as threshold_row_count,
        count(distinct cms_year) as threshold_year_count,
        max(cms_year) as threshold_year
    from {{ ref('int_county_screening_threshold') }}
)

select *
from latest_years
cross join threshold_years
where latest_year_count <> 1
   or threshold_row_count <> 1
   or threshold_year_count <> 1
   or latest_year <> threshold_year
