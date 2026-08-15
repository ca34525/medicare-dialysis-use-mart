{{ config(materialized="table", contract={"enforced": true}) }}

with build_audit as (
    select * from {{ source('raw', 'build_input_audit') }}
),

latest_year as (
    select year
    from {{ ref('dim_year') }}
    where is_latest_cms_year
),

current_county_rows as (
    select
        fact.benes_op_dlys_pct,
        fact.benes_op_dlys_pct_status
    from {{ ref('fct_medicare_county_year') }} as fact
    inner join latest_year on fact.year = latest_year.year
    inner join {{ ref('dim_county') }} as county
        on fact.county_fips = county.county_fips
       and county.is_current_county
),

threshold_metrics as (
    select
        count(*) as current_county_count,
        count(*) filter (
            where benes_op_dlys_pct_status = 'reported'
              and benes_op_dlys_pct is not null
        ) as threshold_eligible_count,
        count(*) filter (
            where benes_op_dlys_pct_status <> 'reported'
               or benes_op_dlys_pct is null
        ) as threshold_excluded_count,
        cast(
            quantile_cont(benes_op_dlys_pct, 0.75) filter (
                where benes_op_dlys_pct_status = 'reported'
                  and benes_op_dlys_pct is not null
            )
            as decimal(38, 10)
        ) as dialysis_use_p75_threshold
    from current_county_rows
),

cms_lineage as (
    select distinct
        fact.source_manifest_run_id,
        fact.source_content_sha256,
        fact.source_retrieved_at_utc,
        fact.source_modified_at
    from {{ ref('fct_medicare_county_year') }} as fact
    inner join latest_year on fact.year = latest_year.year
),

svi_lineage as (
    select distinct
        svi_vintage,
        source_manifest_run_id,
        source_snapshot_sha256,
        source_retrieved_at_utc,
        source_modified_at
    from {{ ref('fct_svi_county') }}
)

select
    cast('county_screening.v1' as varchar) as screening_definition_version,
    build_audit.build_id as screening_run_id,
    build_audit.input_set_sha256,
    build_audit.build_format_version,
    latest_year.year as cms_year,
    svi_lineage.svi_vintage,
    cast('BENES_OP_DLYS_PCT' as varchar) as threshold_metric,
    cast(0.75 as decimal(3, 2)) as threshold_quantile,
    cast('continuous_linear_type_7' as varchar) as threshold_method,
    threshold_metrics.dialysis_use_p75_threshold,
    threshold_metrics.current_county_count,
    threshold_metrics.threshold_eligible_count,
    threshold_metrics.threshold_excluded_count,
    cms_lineage.source_manifest_run_id as cms_source_manifest_run_id,
    cms_lineage.source_content_sha256 as cms_source_content_sha256,
    cms_lineage.source_retrieved_at_utc as cms_source_retrieved_at_utc,
    cms_lineage.source_modified_at as cms_source_modified_at,
    svi_lineage.source_manifest_run_id as svi_source_manifest_run_id,
    svi_lineage.source_snapshot_sha256 as svi_source_snapshot_sha256,
    svi_lineage.source_retrieved_at_utc as svi_source_retrieved_at_utc,
    svi_lineage.source_modified_at as svi_source_modified_at
from build_audit
cross join latest_year
cross join threshold_metrics
cross join cms_lineage
cross join svi_lineage
