{% set families = ['survival', 'hospitalization', 'readmission'] %}

{% for family in families %}
select ccn, '{{ family }}' as measure_family
from {{ ref('stg_cms_dialysis_facility') }}
where {{ family }}_availability_status = 'available'
  and not (
      {{ family }}_lower_confidence_limit <= {{ family }}_estimate
      and {{ family }}_estimate <= {{ family }}_upper_confidence_limit
  )
{% if not loop.last %}union all{% endif %}
{% endfor %}
