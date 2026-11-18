{#
  One row per US barcode. category_main comes from Open Food Facts' tags
  (int_product_tag_categories); products with no mapped tag keep it null for phase 3's model
  to fill. category_source says which applied.
#}

with products as (
    select * from {{ ref('stg_off__products') }}
),

mapped as (
    select * from {{ ref('int_product_tag_categories') }}
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
