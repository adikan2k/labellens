{#
  Per product: how many additives it lists and whether any is on the swap rule's flag list
  (dim_additives.flagged). One row per product in dim_products.
#}

select
    p.code,
    count(b.additive_id)::integer as additive_count,
    coalesce(bool_or(a.flagged), false) as has_flagged_additive
from {{ ref('dim_products') }} as p
left join {{ ref('bridge_product_additives') }} as b using (code)
left join {{ ref('dim_additives') }} as a using (additive_id)
group by p.code
