select
    a.code,
    a.additive_id
from {{ ref('stg_off__product_additives') }} as a
inner join {{ ref('dim_products') }} as p using (code)
