with national_threshold as (
    select dialysis_use_p75_threshold
    from {{ ref('int_county_screening_threshold') }}
),

state_thresholds as (
    select
        state_fips,
        count(distinct dialysis_use_p75_threshold) as threshold_count,
        min(dialysis_use_p75_threshold) as state_threshold
    from {{ ref('mart_county_screening') }}
    group by state_fips
)

select state_thresholds.*
from state_thresholds
cross join national_threshold
where threshold_count <> 1
   or state_threshold is distinct from national_threshold.dialysis_use_p75_threshold
