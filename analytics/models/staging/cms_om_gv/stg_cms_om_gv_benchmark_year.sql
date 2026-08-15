{{ config(contract={"enforced": true}) }}

with benchmark_rows as (
    select *
    from {{ source('raw', 'cms_om_gv') }}
    where "BENE_AGE_LVL" = 'All'
      and (
          (
              "BENE_GEO_LVL" = 'State'
              and regexp_full_match(trim("BENE_GEO_CD"), '[0-9]{2}')
              and trim("BENE_GEO_CD") not in ('60', '66', '69', '72', '78')
          ) or (
              "BENE_GEO_LVL" = 'National'
              and upper(trim("BENE_GEO_DESC")) = 'NATIONAL'
              and coalesce(trim("BENE_GEO_CD"), '') = ''
          )
      )
),

identified as (
    select
        case
            when "BENE_GEO_LVL" = 'National' then 'national'
            else 'state'
        end as benchmark_geography_type,
        case
            when "BENE_GEO_LVL" = 'National' then 'US'
            else trim("BENE_GEO_CD")
        end as benchmark_geography_key,
        *
    from benchmark_rows
),

typed as (
    select
        benchmark_geography_type,
        benchmark_geography_key,
        cast("YEAR" as integer) as year,
        "BENE_GEO_LVL" as source_geography_level,
        "BENE_GEO_DESC" as source_geography_description,
        "BENE_GEO_CD" as source_geography_code,
        "BENE_AGE_LVL" as source_age_level,

        "BENES_OM_CNT" as benes_om_cnt_raw,
        {{ cms_count_value('"BENES_OM_CNT"') }} as benes_om_cnt,
        {{ cms_count_status('"BENES_OM_CNT"') }} as benes_om_cnt_status,

        "MA_PRTCPTN_RATE" as ma_prtcptn_rate_raw,
        {{ cms_numeric_value('"MA_PRTCPTN_RATE"', 'decimal(38, 10)') }}
            as ma_prtcptn_rate,
        {{ cms_numeric_status('"MA_PRTCPTN_RATE"', 'decimal(38, 10)') }}
            as ma_prtcptn_rate_status,

        "BENE_DUAL_PCT" as bene_dual_pct_raw,
        {{ cms_numeric_value('"BENE_DUAL_PCT"', 'decimal(38, 10)') }}
            as bene_dual_pct,
        {{ cms_numeric_status('"BENE_DUAL_PCT"', 'decimal(38, 10)') }}
            as bene_dual_pct_status,

        "BENES_OP_DLYS_CNT" as benes_op_dlys_cnt_raw,
        {{ cms_count_value('"BENES_OP_DLYS_CNT"') }} as benes_op_dlys_cnt,
        {{ cms_count_status('"BENES_OP_DLYS_CNT"') }}
            as benes_op_dlys_cnt_status,

        "BENES_OP_DLYS_PCT" as benes_op_dlys_pct_raw,
        {{ cms_numeric_value('"BENES_OP_DLYS_PCT"', 'decimal(38, 10)') }}
            as benes_op_dlys_pct,
        {{ cms_numeric_status('"BENES_OP_DLYS_PCT"', 'decimal(38, 10)') }}
            as benes_op_dlys_pct_status,

        "OP_DLYS_VISITS_PER_1000_BENES" as op_dlys_visits_per_1000_benes_raw,
        {{ cms_numeric_value(
            '"OP_DLYS_VISITS_PER_1000_BENES"',
            'decimal(38, 10)'
        ) }} as op_dlys_visits_per_1000_benes,
        {{ cms_numeric_status(
            '"OP_DLYS_VISITS_PER_1000_BENES"',
            'decimal(38, 10)'
        ) }} as op_dlys_visits_per_1000_benes_status,

        "OP_DLYS_MDCR_STDZD_PYMT_PC" as op_dlys_mdcr_stdzd_pymt_pc_raw,
        {{ cms_numeric_value(
            '"OP_DLYS_MDCR_STDZD_PYMT_PC"',
            'decimal(38, 10)'
        ) }} as op_dlys_mdcr_stdzd_pymt_pc,
        {{ cms_numeric_status(
            '"OP_DLYS_MDCR_STDZD_PYMT_PC"',
            'decimal(38, 10)'
        ) }} as op_dlys_mdcr_stdzd_pymt_pc_status,

        "ACUTE_HOSP_READMSN_PCT" as acute_hosp_readmsn_pct_raw,
        {{ cms_numeric_value('"ACUTE_HOSP_READMSN_PCT"', 'decimal(38, 10)') }}
            as acute_hosp_readmsn_pct,
        {{ cms_numeric_status('"ACUTE_HOSP_READMSN_PCT"', 'decimal(38, 10)') }}
            as acute_hosp_readmsn_pct_status,

        "ER_VISITS_PER_1000_BENES" as er_visits_per_1000_benes_raw,
        {{ cms_numeric_value(
            '"ER_VISITS_PER_1000_BENES"',
            'decimal(38, 10)'
        ) }} as er_visits_per_1000_benes,
        {{ cms_numeric_status(
            '"ER_VISITS_PER_1000_BENES"',
            'decimal(38, 10)'
        ) }} as er_visits_per_1000_benes_status,

        source_id,
        source_manifest_run_id,
        source_content_sha256,
        source_retrieved_at_utc,
        source_modified_at
    from identified
)

select * from typed
