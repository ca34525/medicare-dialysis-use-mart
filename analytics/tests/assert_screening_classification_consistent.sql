select *
from {{ ref('mart_county_screening') }}
where is_dialysis_use_threshold_eligible
        <> (benes_op_dlys_pct_status = 'reported' and benes_op_dlys_pct is not null)
   or (
        is_dialysis_use_threshold_eligible
        and is_higher_observed_dialysis_use
            <> (benes_op_dlys_pct >= dialysis_use_p75_threshold)
   )
   or (
        not is_dialysis_use_threshold_eligible
        and is_higher_observed_dialysis_use is not null
   )
   or dialysis_use_band <> case
        when not is_dialysis_use_threshold_eligible then 'insufficient_data'
        when benes_op_dlys_pct >= dialysis_use_p75_threshold then 'higher_use'
        else 'lower_use'
   end
   or (
        rpl_themes_status = 'reported'
        and rpl_themes is not null
        and is_higher_social_vulnerability <> (rpl_themes >= 0.75)
   )
   or (
        (rpl_themes_status <> 'reported' or rpl_themes is null)
        and is_higher_social_vulnerability is not null
   )
   or social_vulnerability_band <> case
        when rpl_themes_status <> 'reported' or rpl_themes is null
            then 'insufficient_data'
        when rpl_themes >= 0.75 then 'higher_vulnerability'
        else 'lower_vulnerability'
   end
   or screening_data_status <> case
        when is_dialysis_use_threshold_eligible
         and rpl_themes_status = 'reported'
         and rpl_themes is not null then 'complete'
        else 'insufficient_data'
   end
   or screening_insufficient_reason is distinct from case
        when is_dialysis_use_threshold_eligible
         and rpl_themes_status = 'reported'
         and rpl_themes is not null then cast(null as varchar)
        when not is_dialysis_use_threshold_eligible
         and (rpl_themes_status <> 'reported' or rpl_themes is null)
            then 'both_components_unavailable'
        when not is_dialysis_use_threshold_eligible
            then 'dialysis_use_component_unavailable'
        else 'social_vulnerability_component_unavailable'
   end
   or screening_quadrant <> case
        when screening_data_status = 'insufficient_data' then 'insufficient_data'
        when is_higher_observed_dialysis_use
         and is_higher_social_vulnerability
            then 'higher_use_higher_vulnerability'
        when is_higher_observed_dialysis_use
            then 'higher_use_lower_vulnerability'
        when is_higher_social_vulnerability
            then 'lower_use_higher_vulnerability'
        else 'lower_use_lower_vulnerability'
   end
