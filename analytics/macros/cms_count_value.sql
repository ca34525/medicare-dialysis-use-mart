{% macro cms_count_value(expression) -%}
case
    when regexp_full_match(trim({{ expression }}), '[0-9]+')
        then try_cast(trim({{ expression }}) as decimal(38, 0))
    else null
end
{%- endmacro %}
