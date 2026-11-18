{{ config(materialized='view') }}

{#
  Explainers the model wrote, one per additive and per common ingredient
  (pipeline/enrich/explainers.py). Invalid ones are left out.
#}

select 'additive' as kind, ref as id, value as text, model, prompt_version
from {{ enrich_rows('additive_explainers.jsonl') }}
where status = 'ok' and value is not null

union all

select 'ingredient' as kind, ref as id, value as text, model, prompt_version
from {{ enrich_rows('ingredient_explainers.jsonl') }}
where status = 'ok' and value is not null
