{{ config(materialized='view') }}

{#
  Categories the model gave products that Open Food Facts' tags do not place
  (pipeline/enrich/categories.py). One row per barcode; invalid answers (stored as null so
  they are not paid for twice) are left out.
#}

select
    ref as code,
    value as category_id,
    model,
    prompt_version
from {{ enrich_rows('categories.parquet') }}
where status = 'ok' and value is not null
