select *
from {{ ref('stg_cdc_svi_county_2022') }}
where
    {% for prefix in [
        'rpl_themes', 'rpl_theme1', 'rpl_theme2', 'rpl_theme3', 'rpl_theme4',
        'ep_pov150', 'ep_uninsur', 'ep_age65', 'ep_disabl', 'ep_limeng',
        'ep_noveh'
    ] %}
    (
        {{ prefix }}_status not in (
            'reported', 'unavailable_sentinel', 'unavailable_null'
        )
        or ({{ prefix }}_status = 'reported' and {{ prefix }} is null)
        or ({{ prefix }}_status <> 'reported' and {{ prefix }} is not null)
        or (
            {{ prefix }}_raw is null
            and {{ prefix }}_status <> 'unavailable_null'
        )
        or (
            {{ prefix }}_raw is not null
            and trim({{ prefix }}_raw) = '-999'
            and {{ prefix }}_status <> 'unavailable_sentinel'
        )
    ){% if not loop.last %} or{% endif %}
    {% endfor %}
