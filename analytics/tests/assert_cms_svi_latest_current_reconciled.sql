select *
from {{ ref('audit_cms_svi_county_reconciliation') }}
where reconciliation_status <> 'matched'
   or not cms_present
   or not svi_present
   or cms_row_count <> 1
   or svi_row_count <> 1
   or not regexp_full_match(cms_source_content_sha256, '[0-9a-f]{64}')
   or not regexp_full_match(svi_source_snapshot_sha256, '[0-9a-f]{64}')
