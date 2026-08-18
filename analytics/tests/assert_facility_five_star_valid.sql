select ccn
from {{ ref('stg_cms_dialysis_facility') }}
where (
        five_star_availability_status = 'available'
        and (five_star_rating is null or five_star_rating not between 1 and 5)
    )
   or (
        five_star_availability_status = 'not_available'
        and five_star_rating is not null
    )
