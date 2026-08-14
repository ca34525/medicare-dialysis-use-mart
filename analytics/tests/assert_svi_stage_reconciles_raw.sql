with raw_summary as (
    select
        count(*) as row_count,
        count(distinct "STCNTY") as distinct_county_count,
        count(distinct source_snapshot_sha256) as snapshot_count
    from {{ source('raw', 'cdc_svi_county_2022') }}
),

stage_summary as (
    select
        count(*) as row_count,
        count(distinct county_fips) as distinct_county_count,
        count(distinct source_snapshot_sha256) as snapshot_count
    from {{ ref('stg_cdc_svi_county_2022') }}
)

select raw_summary.*, stage_summary.*
from raw_summary
cross join stage_summary
where raw_summary.row_count <> stage_summary.row_count
   or raw_summary.distinct_county_count <> stage_summary.distinct_county_count
   or raw_summary.snapshot_count <> 1
   or stage_summary.snapshot_count <> 1
