with audit_counts as (
    select
        count(*) as row_count,
        count(distinct build_id) as build_id_count,
        count(distinct input_set_sha256) as input_set_count
    from {{ source('raw', 'build_input_audit') }}
)

select *
from audit_counts
where row_count <> 1
   or build_id_count <> 1
   or input_set_count <> 1
