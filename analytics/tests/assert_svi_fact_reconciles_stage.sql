select
    coalesce(stage.county_fips, fact.county_fips) as county_fips,
    coalesce(stage.svi_vintage, fact.svi_vintage) as svi_vintage
from {{ ref('stg_cdc_svi_county_2022') }} as stage
full outer join {{ ref('fct_svi_county') }} as fact
    on stage.county_fips = fact.county_fips
   and stage.svi_vintage = fact.svi_vintage
where stage.county_fips is null
   or fact.county_fips is null
   or stage.acs_period_start is distinct from fact.acs_period_start
   or stage.acs_period_end is distinct from fact.acs_period_end
   {% for prefix in [
       'rpl_themes', 'rpl_theme1', 'rpl_theme2', 'rpl_theme3', 'rpl_theme4',
       'ep_pov150', 'ep_uninsur', 'ep_age65', 'ep_disabl', 'ep_limeng',
       'ep_noveh'
   ] %}
   or stage.{{ prefix }} is distinct from fact.{{ prefix }}
   or stage.{{ prefix }}_status is distinct from fact.{{ prefix }}_status
   {% endfor %}
   or stage.source_id is distinct from fact.source_id
   or stage.source_manifest_run_id is distinct from fact.source_manifest_run_id
   or stage.source_snapshot_sha256 is distinct from fact.source_snapshot_sha256
   or stage.source_retrieved_at_utc is distinct from fact.source_retrieved_at_utc
   or stage.source_modified_at is distinct from fact.source_modified_at
