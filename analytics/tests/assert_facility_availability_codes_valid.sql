select ccn
from {{ ref('stg_cms_dialysis_facility') }}
where five_star_availability_status = 'invalid'
   or survival_availability_status = 'invalid'
   or hospitalization_availability_status = 'invalid'
   or readmission_availability_status = 'invalid'
