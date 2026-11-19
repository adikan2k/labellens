{#
  How each additive is used across named US products, for the additive guide: how many list
  it, the categories that use it most (up to five, "other" left out), and up to six example
  products, best-ranked first. One row per additive in dim_additives; an additive used only
  by unnamed products gets zero and empty lists.
#}

with named as (
    select p.code, p.category_main, r.rank_pos
    from {{ ref('dim_products') }} as p
    join {{ ref('int_product_rank') }} as r using (code)
    where p.name is not null
),

links as (
    select b.additive_id, n.code, n.category_main, n.rank_pos
    from {{ ref('bridge_product_additives') }} as b
    join named as n using (code)
),

counts as (
    select additive_id, count(*) as product_count
    from links
    group by additive_id
),

by_category as (
    select additive_id, category_main as category_id, count(*) as products
    from links
    where category_main is not null and category_main <> 'other'
    group by additive_id, category_main
),

top_categories as (
    select
        additive_id,
        list(
            struct_pack(category_id := category_id, products := products)
            order by products desc, category_id
        )[1:5] as top_categories
    from by_category
    group by additive_id
),

examples as (
    select additive_id, list(code order by rank_pos, code)[1:6] as example_codes
    from links
    group by additive_id
)

select
    a.additive_id,
    coalesce(c.product_count, 0) as product_count,
    coalesce(t.top_categories, []) as top_categories,
    coalesce(e.example_codes, []) as example_codes
from {{ ref('dim_additives') }} as a
left join counts as c using (additive_id)
left join top_categories as t using (additive_id)
left join examples as e using (additive_id)
