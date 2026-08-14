with expected as (
    select count(*) as row_count
    from {{ source('raw', 'cms_om_gv') }}
    where "BENE_GEO_LVL" = 'County'
      and "BENE_AGE_LVL" = 'All'
      and substr("BENE_GEO_CD", 1, 2) not in ('60', '66', '69', '72', '78')
      and not (
          regexp_full_match(trim("BENE_GEO_CD"), '[0-9]{2}000')
          and regexp_full_match(
              upper(trim("BENE_GEO_DESC")),
              '[A-Z]{2}-UNKNOWN'
          )
      )
),

actual as (
    select count(*) as row_count
    from {{ ref('stg_cms_om_gv_county_year') }}
)

select expected.row_count as expected_rows, actual.row_count as actual_rows
from expected cross join actual
where expected.row_count <> actual.row_count
