{{ config(materialized='view') }}

with base as (
    select * from {{ ref('base_off__us_products') }}
),

front as (
    select *, {{ pick_front_image('images', 'lang') }} as front_image
    from base
)

select
    code,
    {{ pick_text('product_name') }} as product_name,
    {{ clean_text("split_part(brands, ',', 1)") }} as brand,
    lang,
    -- 'unknown' and 'not-applicable' are not grades; keep the raw value for the run report.
    case when nutriscore_grade in ('a', 'b', 'c', 'd', 'e') then nutriscore_grade end
        as nutriscore_grade,
    nutriscore_grade as nutriscore_grade_raw,
    case when nova_group between 1 and 4 then nova_group end as nova_group,
    -- 51 products score 1.06 to 1.10 (more fields filled than the score expects): capped
    -- at 1, not blanked. Float32 noise removed the same way as nutrients.
    least(completeness::varchar::double, 1.0) as completeness,
    completeness::varchar::double as completeness_raw,
    case
        when front_image is not null then
            'https://images.openfoodfacts.org/images/products/'
            || {{ off_image_folder('code') }} || '/'
            || front_image.key || '.' || front_image.rev || '.400.jpg'
    end as image_url,
    'https://world.openfoodfacts.org/product/' || code as off_url,
    to_timestamp(last_modified_t) as last_modified_at,
    copies
from front
