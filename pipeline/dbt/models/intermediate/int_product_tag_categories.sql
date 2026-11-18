{#
  The category Open Food Facts' own tags give each product, through category_map. Specific
  tags (priority 2) beat umbrella tags (priority 1), and among equals the later tag wins,
  since lists mostly run general to specific. Tag order alone is not enough: en:appetizers is
  stored after en:pickles, which would file pickles as salty snacks.

  Its own model (moved out of dim_products) so that both dim_products and the inputs for the
  category model can use it without a cycle: dim_products also reads the model's output.
#}

select
    c.code,
    m.category_id
from {{ ref('stg_off__product_categories') }} as c
inner join {{ ref('category_map') }} as m on m.off_tag = c.category_tag
qualify row_number() over (
    partition by c.code order by m.priority desc, c.position desc
) = 1
