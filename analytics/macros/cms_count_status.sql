{% macro cms_count_status(expression) -%}
case
    when coalesce(trim({{ expression }}), '') = '' then 'unavailable_blank'
    when trim({{ expression }}) = '*' then 'suppressed'
    when upper(trim({{ expression }})) = 'NA' then 'unavailable_na'
    when not regexp_full_match(trim({{ expression }}), '[0-9]+')
        then 'invalid_numeric'
    when try_cast(trim({{ expression }}) as decimal(38, 0)) is null
        then 'invalid_numeric'
    else 'reported'
end
{%- endmacro %}
