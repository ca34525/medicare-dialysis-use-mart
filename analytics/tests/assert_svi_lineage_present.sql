select *
from {{ ref('stg_cdc_svi_county_2022') }}
where source_id <> 'cdc_svi_county_2022'
   or coalesce(trim(source_manifest_run_id), '') = ''
   or not regexp_full_match(source_snapshot_sha256, '[0-9a-f]{64}')
   or coalesce(trim(source_retrieved_at_utc), '') = ''
   or source_page_index < 0
   or source_page_offset < 0
   or not regexp_full_match(source_page_sha256, '[0-9a-f]{64}')
   or svi_vintage <> 2022
   or acs_period_start <> 2018
   or acs_period_end <> 2022
