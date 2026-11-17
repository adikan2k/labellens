{# Fails when the model's row count is outside [min_rows, max_rows]. #}
{% test row_count_between(model, min_rows, max_rows) %}
select row_count
from (select count(*) as row_count from {{ model }})
where row_count < {{ min_rows }} or row_count > {{ max_rows }}
{% endtest %}
