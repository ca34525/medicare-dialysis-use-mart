{% macro facility_period_end(value) -%}
cast(try_strptime(split_part(trim({{ value }}), '-', 2), '%d%b%Y') as date)
{%- endmacro %}
