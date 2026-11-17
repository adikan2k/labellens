{{ config(materialized='view') }}

{#
  The seven label nutrients, per 100 g, pivoted from the nutriments list (its "100g" field).
  Values are as Open Food Facts has them; fct_nutrition blanks the impossible ones.
  They are stored as 32-bit floats, so they go through text to come back as written
  (35.7, not 35.70000076).
#}

{% set nutrients = {
    'energy_kcal_100g': 'energy-kcal',
    'sugars_100g': 'sugars',
    'salt_100g': 'salt',
    'fat_100g': 'fat',
    'saturated_fat_100g': 'saturated-fat',
    'fiber_100g': 'fiber',
    'proteins_100g': 'proteins',
} %}

select
    code,
    {%- for column, name in nutrients.items() %}
    list_filter(nutriments, lambda x: x.name = '{{ name }}')[1]."100g"::varchar::double
        as {{ column }}
    {{- "," if not loop.last }}
    {%- endfor %}
from {{ ref('base_off__us_products') }}
