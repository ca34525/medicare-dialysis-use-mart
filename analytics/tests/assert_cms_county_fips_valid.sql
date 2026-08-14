select *
from {{ ref('stg_cms_om_gv_county_year') }}
where not regexp_full_match(county_fips, '[0-9]{5}')
   or (regexp_full_match(upper(trim(source_geography_description)), 'DC-.*')
       and county_fips <> '11001')
