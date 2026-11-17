{#
  Every additive used by at least one US product, with names and facts from Open Food Facts'
  additives taxonomy. Ids missing from the taxonomy keep a row (name falls back to the
  E-number) so the bridge's relationship test holds. explainer is filled in phase 3.
#}

with used as (
    select additive_id, count(*) as product_count
    from {{ ref('stg_off__product_additives') }}
    group by additive_id
),

taxonomy as (
    select * from {{ ref('stg_off__additives') }}
),

joined as (
    select
        used.additive_id,
        nullif('E' || regexp_extract(used.additive_id, ':e(\d+[a-z]*)$', 1), 'E') as e_number,
        taxonomy.name as taxonomy_name,
        taxonomy.classes,
        taxonomy.vegan,
        taxonomy.vegetarian,
        taxonomy.efsa_evaluation_date,
        taxonomy.wikidata_id,
        taxonomy.additive_id is not null as in_taxonomy,
        used.product_count
    from used
    left join taxonomy using (additive_id)
)

select
    additive_id,
    nullif(e_number, '') as e_number,
    {{ capitalise("coalesce(taxonomy_name, nullif(e_number, ''), " ~ name_from_id('additive_id') ~ ")") }}
        as name,
    classes,
    vegan,
    vegetarian,
    efsa_evaluation_date,
    wikidata_id,
    in_taxonomy,
    product_count,
    null::varchar as explainer
from joined
