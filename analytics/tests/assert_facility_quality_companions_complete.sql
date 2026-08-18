{% set families = ['survival', 'hospitalization', 'readmission'] %}

{% for family in families %}
select ccn, '{{ family }}' as measure_family
from {{ ref('stg_cms_dialysis_facility') }}
where {{ family }}_availability_status = 'available'
  and (
      {{ family }}_period_start is null
      or {{ family }}_period_end is null
      or {{ family }}_category not in (
          'better_than_expected', 'as_expected', 'worse_than_expected'
      )
      or {{ family }}_denominator is null
      or {{ family }}_denominator < 0
      or {{ family }}_estimate is null
      or {{ family }}_estimate < 0
      or {{ family }}_lower_confidence_limit is null
      or {{ family }}_lower_confidence_limit < 0
      or {{ family }}_upper_confidence_limit is null
      or {{ family }}_upper_confidence_limit < 0
  )
{% if not loop.last %}union all{% endif %}
{% endfor %}
