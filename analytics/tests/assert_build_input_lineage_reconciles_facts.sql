with build_audit as (
    select * from {{ source('raw', 'build_input_audit') }}
),

cms_lineage as (
    select distinct
        source_id,
        source_manifest_run_id,
        source_content_sha256,
        source_retrieved_at_utc
    from {{ ref('fct_medicare_county_year') }}
),

svi_lineage as (
    select distinct
        source_id,
        source_manifest_run_id,
        source_snapshot_sha256,
        source_retrieved_at_utc
    from {{ ref('fct_svi_county') }}
),

reconciled as (
    select
        build_audit.*,
        cms.source_id as fact_cms_source_id,
        cms.source_manifest_run_id as fact_cms_manifest_run_id,
        cms.source_content_sha256 as fact_cms_content_sha256,
        cms.source_retrieved_at_utc as fact_cms_retrieved_at_utc,
        svi.source_id as fact_svi_source_id,
        svi.source_manifest_run_id as fact_svi_manifest_run_id,
        svi.source_snapshot_sha256 as fact_svi_snapshot_sha256,
        svi.source_retrieved_at_utc as fact_svi_retrieved_at_utc
    from build_audit
    cross join cms_lineage as cms
    cross join svi_lineage as svi
)

select *
from reconciled
where cms_source_id <> 'cms_om_gv'
   or cms_contract_version <> 'cms_om_gv.raw.v2'
   or svi_source_id <> 'cdc_svi_county_2022'
   or svi_contract_version <> 'cdc_svi_county_2022.raw.v1'
   or cms_source_id <> fact_cms_source_id
   or cms_manifest_run_id <> fact_cms_manifest_run_id
   or cms_content_sha256 <> fact_cms_content_sha256
   or cms_retrieved_at_utc <> fact_cms_retrieved_at_utc
   or svi_source_id <> fact_svi_source_id
   or svi_manifest_run_id <> fact_svi_manifest_run_id
   or svi_snapshot_sha256 <> fact_svi_snapshot_sha256
   or svi_retrieved_at_utc <> fact_svi_retrieved_at_utc
   or not regexp_full_match(input_set_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(cms_content_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(svi_snapshot_sha256, '[0-9a-f]{64}')
   or cms_page_count < 1
   or cms_row_count < 1
   or svi_page_count < 1
   or svi_row_count < 1
