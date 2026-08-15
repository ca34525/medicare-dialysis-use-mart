select count(*) as latest_year_count
from {{ ref('dim_year') }}
having count(*) filter (where is_latest_cms_year) <> 1
    or max(year) <> max(year) filter (where is_latest_cms_year)
