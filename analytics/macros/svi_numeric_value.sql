{% macro svi_numeric_value(expression, data_type='decimal(18, 10)') -%}
case
    when {{ expression }} is null then null
    when trim({{ expression }}) = '-999' then null
    else try_cast(trim({{ expression }}) as {{ data_type }})
end
{%- endmacro %}
