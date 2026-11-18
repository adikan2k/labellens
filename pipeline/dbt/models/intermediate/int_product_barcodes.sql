{#
  Whether each product's code is a real GS1 barcode (macros/barcode.sql). Swaps offer only
  products whose code is: the rest are mostly restaurant menu items and shop-weighed goods.
#}

select
    code,
    {{ gtin_valid('code') }} as gtin_valid
from {{ ref('stg_off__products') }}
