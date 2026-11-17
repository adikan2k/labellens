{#
  Top-level ingredients Open Food Facts recognises, by label position. rank is the position
  on the label (1 = first), so gaps mean an unrecognised entry sat there. When a product
  lists the same ingredient twice, its first position is kept.
#}

select
    i.code,
    i.ingredient_id,
    min(i.position) as rank,
    -- Open Food Facts' estimate; values outside 0 to 100 (seen: -551 to 931) are dropped.
    arg_min(
        case when i.percent_estimate between 0 and 100 then i.percent_estimate end, i.position
    ) as percent_estimate
from {{ ref('stg_off__product_ingredients') }} as i
inner join {{ ref('dim_products') }} as p using (code)
where i.in_taxonomy
group by i.code, i.ingredient_id
