{% macro facility_unavailability_reason(value) -%}
case trim({{ value }})
    when '199' then 'insufficient_patients'
    when '201' then 'data_not_reported'
    when '255' then 'inaccurate_measure'
    when '258' then 'insufficient_history'
    when '260' then 'insufficient_star_data'
    when '261' then 'inaccurate_star_component'
    when '270' then 'disaster_suppression'
    when '280' then 'external_factors'
    when '281' then 'external_factors_star_rating'
    else null
end
{%- endmacro %}
