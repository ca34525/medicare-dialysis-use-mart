{{ config(contract={"enforced": true}) }}

with raw_source as (
    select *
    from {{ source('raw', 'cdc_svi_county_2022') }}
)

select
    "STCNTY" as county_fips,
    "ST" as state_fips,
    "STATE" as state_name,
    "ST_ABBR" as state_abbreviation,
    "COUNTY" as county_name,
    cast("GRASP_ID" as integer) as source_object_id,
    2022 as svi_vintage,
    2018 as acs_period_start,
    2022 as acs_period_end,

    "RPL_THEMES" as rpl_themes_raw,
    {{ svi_numeric_value('"RPL_THEMES"') }} as rpl_themes,
    {{ svi_numeric_status('"RPL_THEMES"') }} as rpl_themes_status,

    "RPL_THEME1" as rpl_theme1_raw,
    {{ svi_numeric_value('"RPL_THEME1"') }} as rpl_theme1,
    {{ svi_numeric_status('"RPL_THEME1"') }} as rpl_theme1_status,

    "RPL_THEME2" as rpl_theme2_raw,
    {{ svi_numeric_value('"RPL_THEME2"') }} as rpl_theme2,
    {{ svi_numeric_status('"RPL_THEME2"') }} as rpl_theme2_status,

    "RPL_THEME3" as rpl_theme3_raw,
    {{ svi_numeric_value('"RPL_THEME3"') }} as rpl_theme3,
    {{ svi_numeric_status('"RPL_THEME3"') }} as rpl_theme3_status,

    "RPL_THEME4" as rpl_theme4_raw,
    {{ svi_numeric_value('"RPL_THEME4"') }} as rpl_theme4,
    {{ svi_numeric_status('"RPL_THEME4"') }} as rpl_theme4_status,

    "EP_POV150" as ep_pov150_raw,
    {{ svi_numeric_value('"EP_POV150"') }} as ep_pov150,
    {{ svi_numeric_status('"EP_POV150"') }} as ep_pov150_status,

    "EP_UNINSUR" as ep_uninsur_raw,
    {{ svi_numeric_value('"EP_UNINSUR"') }} as ep_uninsur,
    {{ svi_numeric_status('"EP_UNINSUR"') }} as ep_uninsur_status,

    "EP_AGE65" as ep_age65_raw,
    {{ svi_numeric_value('"EP_AGE65"') }} as ep_age65,
    {{ svi_numeric_status('"EP_AGE65"') }} as ep_age65_status,

    "EP_DISABL" as ep_disabl_raw,
    {{ svi_numeric_value('"EP_DISABL"') }} as ep_disabl,
    {{ svi_numeric_status('"EP_DISABL"') }} as ep_disabl_status,

    "EP_LIMENG" as ep_limeng_raw,
    {{ svi_numeric_value('"EP_LIMENG"') }} as ep_limeng,
    {{ svi_numeric_status('"EP_LIMENG"') }} as ep_limeng_status,

    "EP_NOVEH" as ep_noveh_raw,
    {{ svi_numeric_value('"EP_NOVEH"') }} as ep_noveh,
    {{ svi_numeric_status('"EP_NOVEH"') }} as ep_noveh_status,

    source_id,
    source_manifest_run_id,
    source_snapshot_sha256,
    source_retrieved_at_utc,
    source_modified_at,
    source_page_index,
    source_page_offset,
    source_page_sha256
from raw_source
