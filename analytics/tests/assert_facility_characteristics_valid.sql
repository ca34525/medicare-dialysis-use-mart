select ccn
from {{ ref('stg_cms_dialysis_facility') }}
where dialysis_stations is null
   or dialysis_stations < 0
   or lower(trim(chain_owned_raw)) not in ('yes', 'no')
   or lower(trim(in_center_hemodialysis_raw)) not in ('yes', 'no')
   or lower(trim(peritoneal_dialysis_raw)) not in ('yes', 'no')
   or lower(trim(home_hemodialysis_training_raw)) not in ('yes', 'no')
   or certification_date is null
