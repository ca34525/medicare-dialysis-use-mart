with lineage as (
    select distinct
        source_id,
        source_manifest_run_id,
        source_content_sha256,
        source_retrieved_at_utc,
        source_modified_at
    from {{ ref('fct_medicare_county_year') }}
    union
    select distinct
        source_id,
        source_manifest_run_id,
        source_content_sha256,
        source_retrieved_at_utc,
        source_modified_at
    from {{ ref('fct_medicare_benchmark_year') }}
)

select count(*) as lineage_set_count
from lineage
having count(*) <> 1
    or min(source_id) <> 'cms_om_gv'
    or not regexp_full_match(min(source_content_sha256), '[0-9a-f]{64}')
