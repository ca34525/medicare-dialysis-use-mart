with facts as (
    select
        'county' as fact_type,
        county_fips as geography_key,
        year,
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
        er_visits_per_1000_benes_status
    from {{ ref('fct_medicare_county_year') }}
    union all by name
    select
        benchmark_geography_type as fact_type,
        benchmark_geography_key as geography_key,
        year,
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
        er_visits_per_1000_benes_status
    from {{ ref('fct_medicare_benchmark_year') }}
)

select *
from facts
where benes_om_cnt < 0
   or benes_op_dlys_cnt < 0
   or op_dlys_visits_per_1000_benes < 0
   or op_dlys_mdcr_stdzd_pymt_pc < 0
   or er_visits_per_1000_benes < 0
   or ma_prtcptn_rate not between 0 and 1
   or bene_dual_pct not between 0 and 1
   or benes_op_dlys_pct not between 0 and 1
   or acute_hosp_readmsn_pct not between 0 and 1
   {% for prefix in [
       'benes_om_cnt', 'ma_prtcptn_rate', 'bene_dual_pct',
       'benes_op_dlys_cnt', 'benes_op_dlys_pct',
       'op_dlys_visits_per_1000_benes', 'op_dlys_mdcr_stdzd_pymt_pc',
       'acute_hosp_readmsn_pct', 'er_visits_per_1000_benes'
   ] %}
   or {{ prefix }}_status not in (
       'reported', 'suppressed', 'unavailable_blank', 'unavailable_na'
   )
   or ({{ prefix }}_status = 'reported' and {{ prefix }} is null)
   or ({{ prefix }}_status <> 'reported' and {{ prefix }} is not null)
   {% endfor %}
