with screening as (
    select * from {{ ref('mart_county_screening') }}
),

reconciled as (
    select
        screening.*,
        cms.benes_om_cnt as fact_benes_om_cnt,
        cms.benes_om_cnt_status as fact_benes_om_cnt_status,
        cms.benes_op_dlys_pct as fact_benes_op_dlys_pct,
        cms.benes_op_dlys_pct_status as fact_benes_op_dlys_pct_status,
        cms.source_manifest_run_id as fact_cms_manifest_run_id,
        cms.source_content_sha256 as fact_cms_content_sha256,
        svi.rpl_themes as fact_rpl_themes,
        svi.rpl_themes_status as fact_rpl_themes_status,
        svi.source_manifest_run_id as fact_svi_manifest_run_id,
        svi.source_snapshot_sha256 as fact_svi_snapshot_sha256
    from screening
    left join {{ ref('fct_medicare_county_year') }} as cms
        on screening.county_fips = cms.county_fips
       and screening.cms_year = cms.year
    left join {{ ref('fct_svi_county') }} as svi
        on screening.county_fips = svi.county_fips
       and screening.svi_vintage = svi.svi_vintage
)

select *
from reconciled
where benes_om_cnt is distinct from fact_benes_om_cnt
   or benes_om_cnt_status <> fact_benes_om_cnt_status
   or benes_op_dlys_pct is distinct from fact_benes_op_dlys_pct
   or benes_op_dlys_pct_status <> fact_benes_op_dlys_pct_status
   or rpl_themes is distinct from fact_rpl_themes
   or rpl_themes_status <> fact_rpl_themes_status
   or cms_source_manifest_run_id <> fact_cms_manifest_run_id
   or cms_source_content_sha256 <> fact_cms_content_sha256
   or svi_source_manifest_run_id <> fact_svi_manifest_run_id
   or svi_source_snapshot_sha256 <> fact_svi_snapshot_sha256
   or not regexp_full_match(input_set_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(cms_source_content_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(svi_source_snapshot_sha256, '[0-9a-f]{64}')
