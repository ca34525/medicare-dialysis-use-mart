with counts as (
    select
        (select count(*) from {{ source('raw', 'cms_dialysis_facility') }})
            as raw_rows,
        (select count(distinct "CMS Certification Number (CCN)")
         from {{ source('raw', 'cms_dialysis_facility') }}) as raw_distinct_ccns,
        (select count(*) from {{ ref('stg_cms_dialysis_facility') }})
            as stage_rows,
        (select count(distinct ccn) from {{ ref('stg_cms_dialysis_facility') }})
            as stage_distinct_ccns,
        (select row_count
         from {{ source('raw', 'cms_dialysis_facility_load_audit') }})
            as audit_rows,
        (select distinct_ccn_count
         from {{ source('raw', 'cms_dialysis_facility_load_audit') }})
            as audit_distinct_ccns
)

select *
from counts
where raw_rows != raw_distinct_ccns
   or raw_rows != stage_rows
   or stage_rows != stage_distinct_ccns
   or stage_rows != audit_rows
   or stage_distinct_ccns != audit_distinct_ccns
