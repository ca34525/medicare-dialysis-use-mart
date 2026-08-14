{% macro svi_numeric_status(expression, data_type='decimal(18, 10)') -%}
case
    when {{ expression }} is null then 'unavailable_null'
    when trim({{ expression }}) = '-999' then 'unavailable_sentinel'
    when try_cast(trim({{ expression }}) as {{ data_type }}) is null
        then 'invalid_numeric'
    else 'reported'
end
{%- endmacro %}
