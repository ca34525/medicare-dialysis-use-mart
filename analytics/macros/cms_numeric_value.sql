{% macro cms_numeric_value(expression, data_type) -%}
try_cast(trim({{ expression }}) as {{ data_type }})
{%- endmacro %}
