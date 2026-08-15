with stage as (
    select
        benchmark_geography_type,
        benchmark_geography_key,
        year,
        source_geography_description,
        source_geography_code,
        benes_om_cnt,
        benes_om_cnt_status,
        ma_prtcptn_rate,
        ma_prtcptn_rate_status,
        bene_dual_pct,
        bene_dual_pct_status,
        benes_op_dlys_cnt,
        benes_op_dlys_cnt_status,
        benes_op_dlys_pct,
        benes_op_dlys_pct_status,
        op_dlys_visits_per_1000_benes,
        op_dlys_visits_per_1000_benes_status,
        op_dlys_mdcr_stdzd_pymt_pc,
        op_dlys_mdcr_stdzd_pymt_pc_status,
        acute_hosp_readmsn_pct,
        acute_hosp_readmsn_pct_status,
        er_visits_per_1000_benes,
        er_visits_per_1000_benes_status,
        source_id,
        source_manifest_run_id,
        source_content_sha256,
        source_retrieved_at_utc,
        source_modified_at
    from {{ ref('stg_cms_om_gv_benchmark_year') }}
),

differences as (
    (select * from stage except all select * from {{ ref('fct_medicare_benchmark_year') }})
    union all
    (select * from {{ ref('fct_medicare_benchmark_year') }} except all select * from stage)
)

select * from differences
