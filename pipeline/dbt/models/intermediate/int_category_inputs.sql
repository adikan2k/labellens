{#
  What the category model sees for each named product: its name, brand and the start of its
  ingredient list (the label texts in order, cut at 200 characters). Built for every named
  product, so the eval (gold products, some of them tagged) and the fill (untagged products)
  send exactly the same input. tag_category says whether Open Food Facts' tags already gave
  one; scans and completeness order the fill, so a --limit run covers popular products first.
#}

with ingredients as (
    select
        code,
        string_agg(label_text, ', ' order by position) as ingredients
    from {{ ref('stg_off__product_ingredients') }}
    where position <= 20 and label_text is not null
    group by code
)

select
    p.code,
    p.product_name as name,
    p.brand,
    nullif(left(i.ingredients, 200), '') as ingredients,
    t.category_id as tag_category,
    p.scans,
    p.completeness
from {{ ref('stg_off__products') }} as p
left join ingredients as i using (code)
left join {{ ref('int_product_tag_categories') }} as t using (code)
where p.product_name is not null
