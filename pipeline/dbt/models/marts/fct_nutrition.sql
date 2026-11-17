{#
  Per-100 g nutrition, one row per product. A value outside what is physically possible
  (below 0, above 100 g, or above 900 kcal) is blanked, not the whole row; the run report
  counts every blanked value.
#}

{% set limits = {
    'energy_kcal_100g': 900,
    'sugars_100g': 100,
    'salt_100g': 100,
    'fat_100g': 100,
    'saturated_fat_100g': 100,
    'fiber_100g': 100,
    'proteins_100g': 100,
} %}

select
    p.code,
    {%- for column, limit in limits.items() %}
    case when n.{{ column }} between 0 and {{ limit }} then n.{{ column }} end as {{ column }}
    {{- "," if not loop.last }}
    {%- endfor %}
from {{ ref('dim_products') }} as p
left join {{ ref('stg_off__nutrition') }} as n using (code)
