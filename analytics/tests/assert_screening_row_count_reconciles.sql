with counts as (
    select
        (select count(*) from {{ ref('mart_county_screening') }})
            as screening_count,
        (
            select count(*)
            from {{ ref('dim_county') }}
            where is_current_county
        ) as current_county_count,
        (
            select sum(cast(is_dialysis_use_threshold_eligible as integer))
            from {{ ref('mart_county_screening') }}
        ) as eligible_count,
        (
            select threshold_eligible_count
            from {{ ref('int_county_screening_threshold') }}
        ) as threshold_eligible_count
)

select *
from counts
where screening_count <> current_county_count
   or eligible_count <> threshold_eligible_count
