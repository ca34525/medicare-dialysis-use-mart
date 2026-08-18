select ccn
from {{ ref('stg_cms_dialysis_facility') }}
where five_star_period_start is null
   or five_star_period_end is null
   or five_star_period_start > five_star_period_end
   or survival_period_start is null
   or survival_period_end is null
   or survival_period_start > survival_period_end
   or hospitalization_period_start is null
   or hospitalization_period_end is null
   or hospitalization_period_start > hospitalization_period_end
   or readmission_period_start is null
   or readmission_period_end is null
   or readmission_period_start > readmission_period_end
