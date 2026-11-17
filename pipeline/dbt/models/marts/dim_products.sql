{#
  One row per US barcode. category_main comes from category_map: specific tags (priority 2)
  beat umbrella tags (priority 1), and among equals the later tag wins, since lists mostly
  run general to specific. Tag order alone is not enough: en:appetizers is stored after
  en:pickles, which would file pickles as salty snacks. Products with no mapped tag keep
  category_main null for phase 3's model to fill; category_source says which applied.
#}

with products as (
    select * from {{ ref('stg_off__products') }}
),

mapped as (
    select
        c.code,
        m.category_id
    from {{ ref('stg_off__product_categories') }} as c
    inner join {{ ref('category_map') }} as m on m.off_tag = c.category_tag
    qualify row_number() over (
        partition by c.code order by m.priority desc, c.position desc
    ) = 1
)

select
    p.code,
    p.product_name as name,
    p.brand,
    mapped.category_id as category_main,
    case when mapped.category_id is not null then 'off_tags' end as category_source,
    p.nutriscore_grade,
    p.nova_group,
    p.image_url,
    p.off_url,
    p.completeness,
    p.scans,
    p.lang,
    p.last_modified_at
from products as p
left join mapped using (code)
