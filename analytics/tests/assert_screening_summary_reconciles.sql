with mart_totals as (
    select
        count(*) as total_screening_row_count,
        count(*) filter (
            where screening_data_status = 'complete'
        ) as complete_data_count,
        count(*) filter (
            where screening_data_status = 'insufficient_data'
        ) as insufficient_data_count,
        count(*) filter (
            where is_higher_observed_dialysis_use
        ) as higher_use_count,
        count(*) filter (
            where is_higher_observed_dialysis_use = false
        ) as lower_use_count,
        count(*) filter (
            where is_higher_social_vulnerability
        ) as higher_vulnerability_count,
        count(*) filter (
            where is_higher_social_vulnerability = false
        ) as lower_vulnerability_count
    from {{ ref('mart_county_screening') }}
),

summary_totals as (
    select
        count(*) as category_count,
        count(distinct screening_quadrant) as distinct_category_count,
        count(distinct category_display_order) as distinct_order_count,
        sum(screening_row_count) as category_row_sum,
        sum(screening_row_count) filter (
            where screening_quadrant <> 'insufficient_data'
        ) as complete_category_sum,
        sum(screening_row_count) filter (
            where screening_quadrant = 'insufficient_data'
        ) as insufficient_category_sum,
        min(screening_row_count) as minimum_category_count,
        count(distinct screening_run_id) as run_count,
        count(distinct input_set_sha256) as input_set_count,
        count(distinct dialysis_use_p75_threshold) as threshold_count,
        count(distinct cms_year) as cms_year_count,
        count(distinct svi_vintage) as svi_vintage_count,
        max(total_screening_row_count) as repeated_total,
        max(complete_data_count) as repeated_complete,
        max(insufficient_data_count) as repeated_insufficient,
        max(higher_use_count) as repeated_higher_use,
        max(lower_use_count) as repeated_lower_use,
        max(higher_vulnerability_count) as repeated_higher_vulnerability,
        max(lower_vulnerability_count) as repeated_lower_vulnerability,
        max(threshold_eligible_count) as threshold_eligible_count,
        max(threshold_excluded_count) as threshold_excluded_count
    from {{ ref('audit_screening_quadrant_summary') }}
),

invalid_categories as (
    select count(*) as invalid_count
    from {{ ref('audit_screening_quadrant_summary') }}
    where (category_display_order, screening_quadrant) not in (
        (1, 'higher_use_higher_vulnerability'),
        (2, 'higher_use_lower_vulnerability'),
        (3, 'lower_use_higher_vulnerability'),
        (4, 'lower_use_lower_vulnerability'),
        (5, 'insufficient_data')
    )
)

select *
from summary_totals
cross join mart_totals
cross join invalid_categories
where category_count <> 5
   or distinct_category_count <> 5
   or distinct_order_count <> 5
   or minimum_category_count < 0
   or invalid_count <> 0
   or run_count <> 1
   or input_set_count <> 1
   or threshold_count <> 1
   or cms_year_count <> 1
   or svi_vintage_count <> 1
   or category_row_sum <> mart_totals.total_screening_row_count
   or repeated_total <> mart_totals.total_screening_row_count
   or complete_category_sum <> mart_totals.complete_data_count
   or repeated_complete <> mart_totals.complete_data_count
   or insufficient_category_sum <> mart_totals.insufficient_data_count
   or repeated_insufficient <> mart_totals.insufficient_data_count
   or repeated_higher_use <> mart_totals.higher_use_count
   or repeated_lower_use <> mart_totals.lower_use_count
   or repeated_higher_vulnerability <> mart_totals.higher_vulnerability_count
   or repeated_lower_vulnerability <> mart_totals.lower_vulnerability_count
   or threshold_eligible_count <> mart_totals.higher_use_count + mart_totals.lower_use_count
   or threshold_eligible_count + threshold_excluded_count
        <> mart_totals.total_screening_row_count
