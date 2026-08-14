{% macro cms_numeric_status(expression, data_type) -%}
case
    when coalesce(trim({{ expression }}), '') = '' then 'unavailable_blank'
    when trim({{ expression }}) = '*' then 'suppressed'
    when upper(trim({{ expression }})) = 'NA' then 'unavailable_na'
    when try_cast(trim({{ expression }}) as {{ data_type }}) is null
        then 'invalid_numeric'
    else 'reported'
end
{%- endmacro %}
