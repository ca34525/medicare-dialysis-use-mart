{% macro facility_availability_status(value, measure_type) -%}
case
    when trim({{ value }}) = '001' then 'available'
    when trim({{ value }}) in (
        '199', '201', '255', '258', '270', '280'
        {%- if measure_type == 'star' %}, '260', '261', '281'{% endif %}
    ) then 'not_available'
    else 'invalid'
end
{%- endmacro %}
