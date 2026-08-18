with build_audit as (
    select * from {{ source('raw', 'build_input_audit') }}
),

facility_lineage as (
    select distinct
        source_id,
        source_manifest_run_id,
        source_snapshot_sha256,
        source_retrieved_at_utc
    from {{ ref('fct_facility_quality_snapshot') }}
),

counts as (
    select
        (select count(*) from {{ ref('stg_cms_dialysis_facility') }})
            as stage_rows,
        (select count(*) from {{ ref('dim_facility') }}) as dimension_rows,
        (select count(*) from {{ ref('fct_facility_quality_snapshot') }})
            as fact_rows
),

reconciled as (
    select
        counts.*,
        build_audit.*,
        facility_lineage.source_id as fact_facility_source_id,
        facility_lineage.source_manifest_run_id
            as fact_facility_manifest_run_id,
        facility_lineage.source_snapshot_sha256
            as fact_facility_snapshot_sha256,
        facility_lineage.source_retrieved_at_utc
            as fact_facility_retrieved_at_utc
    from counts
    cross join build_audit
    cross join facility_lineage
)

select *
from reconciled
where stage_rows != dimension_rows
   or stage_rows != fact_rows
   or build_format_version <> 2
   or facility_source_id is null
   or facility_source_id <> 'cms_dialysis_facility'
   or facility_contract_version is null
   or facility_contract_version <> 'cms_dialysis_facility.raw.v1'
   or facility_manifest_run_id is null
   or facility_snapshot_sha256 is null
   or facility_retrieved_at_utc is null
   or facility_page_count is null
   or facility_row_count is null
   or facility_source_id <> fact_facility_source_id
   or facility_manifest_run_id <> fact_facility_manifest_run_id
   or facility_snapshot_sha256 <> fact_facility_snapshot_sha256
   or facility_retrieved_at_utc <> fact_facility_retrieved_at_utc
   or not regexp_full_match(input_set_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(facility_snapshot_sha256, '[0-9a-f]{64}')
   or facility_page_count <> 1
   or facility_row_count < 1
