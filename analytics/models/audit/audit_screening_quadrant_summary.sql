{{ config(materialized="table", contract={"enforced": true}) }}

with categories as (
    select *
    from (
        values
            (1, 'higher_use_higher_vulnerability'),
            (2, 'higher_use_lower_vulnerability'),
            (3, 'lower_use_higher_vulnerability'),
            (4, 'lower_use_lower_vulnerability'),
            (5, 'insufficient_data')
    ) as category_values(category_display_order, screening_quadrant)
),

category_counts as (
    select
        screening_quadrant,
        count(*) as screening_row_count
    from {{ ref('mart_county_screening') }}
    group by screening_quadrant
),

run_totals as (
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

threshold as (
    select * from {{ ref('int_county_screening_threshold') }}
)

select
    threshold.screening_definition_version,
    threshold.screening_run_id,
    threshold.input_set_sha256,
    threshold.cms_year,
    threshold.svi_vintage,
    categories.category_display_order,
    categories.screening_quadrant,
    coalesce(category_counts.screening_row_count, 0) as screening_row_count,
    run_totals.total_screening_row_count,
    run_totals.complete_data_count,
    run_totals.insufficient_data_count,
    run_totals.higher_use_count,
    run_totals.lower_use_count,
    run_totals.higher_vulnerability_count,
    run_totals.lower_vulnerability_count,
    threshold.dialysis_use_p75_threshold,
    threshold.threshold_eligible_count,
    threshold.threshold_excluded_count,
    threshold.cms_source_manifest_run_id,
    threshold.cms_source_content_sha256,
    threshold.svi_source_manifest_run_id,
    threshold.svi_source_snapshot_sha256
from categories
left join category_counts using (screening_quadrant)
cross join run_totals
cross join threshold
