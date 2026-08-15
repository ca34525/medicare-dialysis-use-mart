{% set status_columns = [
    'benes_om_cnt_status',
    'ma_prtcptn_rate_status',
    'bene_dual_pct_status',
    'benes_op_dlys_cnt_status',
    'benes_op_dlys_pct_status',
    'op_dlys_visits_per_1000_benes_status',
    'op_dlys_mdcr_stdzd_pymt_pc_status',
    'acute_hosp_readmsn_pct_status',
    'er_visits_per_1000_benes_status'
] %}

select *
from {{ ref('stg_cms_om_gv_benchmark_year') }}
where
{% for column in status_columns %}
    {{ column }} = 'invalid_numeric'{% if not loop.last %} or{% endif %}
{% endfor %}
