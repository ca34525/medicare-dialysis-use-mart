select *
from {{ ref('stg_cms_om_gv_county_year') }}
where source_id <> 'cms_om_gv'
   or coalesce(trim(source_manifest_run_id), '') = ''
   or not regexp_full_match(source_content_sha256, '[0-9a-f]{64}')
   or coalesce(trim(source_retrieved_at_utc), '') = ''
