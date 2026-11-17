{# Fails when the share of null values in the column is above max_share (0 to 1). #}
{% test max_null_share(model, column_name, max_share) %}
select null_share
from (
    select count(*) filter (where {{ column_name }} is null)::double / nullif(count(*), 0) as null_share
    from {{ model }}
)
where null_share > {{ max_share }}
{% endtest %}
