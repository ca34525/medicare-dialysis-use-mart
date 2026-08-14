select *
from {{ ref('stg_cdc_svi_county_2022') }}
where
    {% for prefix in [
        'ep_pov150', 'ep_uninsur', 'ep_age65', 'ep_disabl', 'ep_limeng',
        'ep_noveh'
    ] %}
    ({{ prefix }} is not null and {{ prefix }} not between 0 and 100)
    {% if not loop.last %}or{% endif %}
    {% endfor %}
