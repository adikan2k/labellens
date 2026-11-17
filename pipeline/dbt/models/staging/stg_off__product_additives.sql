{{ config(materialized='view') }}

select distinct
    code,
    trim(additive_id) as additive_id
from (
    select code, unnest(additives_tags) as additive_id
    from {{ ref('base_off__us_products') }}
)
where nullif(trim(additive_id), '') is not null
