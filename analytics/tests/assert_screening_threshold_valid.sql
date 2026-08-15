select *
from {{ ref('int_county_screening_threshold') }}
where screening_definition_version <> 'county_screening.v1'
   or threshold_metric <> 'BENES_OP_DLYS_PCT'
   or threshold_quantile <> 0.75
   or threshold_method <> 'continuous_linear_type_7'
   or current_county_count <> threshold_eligible_count + threshold_excluded_count
   or threshold_eligible_count < 1
   or threshold_excluded_count < 0
   or dialysis_use_p75_threshold < 0
   or dialysis_use_p75_threshold > 1
   or not regexp_full_match(input_set_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(cms_source_content_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(svi_source_snapshot_sha256, '[0-9a-f]{64}')
