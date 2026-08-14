select *
from {{ ref('stg_cdc_svi_county_2022') }}
where
    {% for prefix in [
        'rpl_themes', 'rpl_theme1', 'rpl_theme2', 'rpl_theme3', 'rpl_theme4'
    ] %}
    ({{ prefix }} is not null and {{ prefix }} not between 0 and 1)
    {% if not loop.last %}or{% endif %}
    {% endfor %}
