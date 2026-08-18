{% macro facility_period_start(value) -%}
cast(try_strptime(split_part(trim({{ value }}), '-', 1), '%d%b%Y') as date)
{%- endmacro %}
