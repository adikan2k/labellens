{#
  One row per US barcode. category_main comes from Open Food Facts' tags
  (int_product_tag_categories) when they give one, otherwise from the model
  (stg_enrich__categories, phase 3). category_source says which: 'off_tags' or 'model'.
  Tags win if both exist, which happens when a product gains tags after the model ran.
#}

with products as (
    select * from {{ ref('stg_off__products') }}
),

mapped as (
    select * from {{ ref('int_product_tag_categories') }}
),

suggested as (
    select code, category_id from {{ ref('stg_enrich__categories') }}
),

barcodes as (
    select * from {{ ref('int_product_barcodes') }}
)

select
    p.code,
    p.product_name as name,
    p.brand,
    coalesce(mapped.category_id, suggested.category_id) as category_main,
    case
        when mapped.category_id is not null then 'off_tags'
        when suggested.category_id is not null then 'model'
    end as category_source,
    p.nutriscore_grade,
    p.nova_group,
    p.image_url,
    p.off_url,
    barcodes.gtin_valid,
    p.completeness,
    p.scans,
    p.lang,
    p.last_modified_at
from products as p
left join mapped using (code)
left join suggested using (code)
join barcodes using (code)
