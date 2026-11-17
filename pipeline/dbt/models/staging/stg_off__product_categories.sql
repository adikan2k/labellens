{{ config(materialized='view') }}

{# Open Food Facts category tags in their stored order (general to specific). #}

with tags as (
    select
        code,
        unnest(range(1, len(categories_tags) + 1))::integer as position,
        unnest(categories_tags) as category_tag
    from {{ ref('base_off__us_products') }}
    where len(categories_tags) > 0
)

select code, position, category_tag
from tags
where category_tag <> 'en:undefined'
