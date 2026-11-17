{{ config(materialized='view') }}

{#
  Top-level ingredients in label order, from the `ingredients` JSON. Every entry is kept with
  its taxonomy flag; the marts keep only entries Open Food Facts recognises.
#}

with parsed as (
    select code, from_json(ingredients, '["JSON"]') as entries
    from {{ ref('base_off__us_products') }}
    where ingredients is not null
),

entries as (
    select
        code,
        unnest(range(1, len(entries) + 1)) as position,
        unnest(entries) as entry
    from parsed
)

select
    code,
    position::integer as position,
    json_extract_string(entry, '$.id') as ingredient_id,
    {{ clean_text("json_extract_string(entry, '$.text')") }} as label_text,
    coalesce(json_extract_string(entry, '$.is_in_taxonomy') = '1', false) as in_taxonomy,
    try_cast(json_extract_string(entry, '$.percent_estimate') as double) as percent_estimate
from entries
where json_extract_string(entry, '$.id') is not null
