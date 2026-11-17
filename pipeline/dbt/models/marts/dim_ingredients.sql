{#
  One row per recognised ingredient used by US products, with a readable name:

  1. Ingredient ids that are additives (en:e330) take the additives taxonomy name (Citric acid).
  2. Other English ids take the most common spelling on English-language products, but only
     spellings that resemble the id (Jaro-Winkler >= 0.7), so 'natural flavor' names
     en:natural-flavouring while a Spanish label on an English product cannot name en:added-sugar.
  3. Otherwise the name comes from the id (en:chicken-fillet -> Chicken fillet), or for
     non-English ids, the most common spelling.

  Footnote marks (*, †, #, _) are stripped. explainer is filled in phase 3.
#}

with uses as (
    select
        i.ingredient_id,
        p.lang = 'en' as english,
        lower(nullif(trim(regexp_replace(i.label_text, '[*†‡#=_%]+', '', 'g')), '')) as label_text,
        lower(replace(split_part(i.ingredient_id, ':', 2), '-', ' ')) as id_words
    from {{ ref('stg_off__product_ingredients') }} as i
    inner join {{ ref('bridge_product_ingredients') }} as b
        on b.code = i.code and b.ingredient_id = i.ingredient_id and b.rank = i.position
    inner join {{ ref('dim_products') }} as p on p.code = i.code
),

named as (
    select
        ingredient_id,
        mode(label_text) filter (
            where english and jaro_winkler_similarity(label_text, id_words) >= 0.7
        ) as english_text,
        mode(label_text) as any_text,
        count(*) as product_count
    from uses
    group by ingredient_id
),

additive_names as (
    select additive_id, name from {{ ref('stg_off__additives') }} where name is not null
)

select
    n.ingredient_id,
    case
        when a.name is not null then {{ capitalise('a.name') }}
        when n.english_text is not null then {{ capitalise('n.english_text') }}
        when n.ingredient_id like 'en:%' then {{ name_from_id('n.ingredient_id') }}
        else {{ capitalise('n.any_text') }}
    end as name,
    n.product_count,
    null::varchar as explainer
from named as n
left join additive_names as a on a.additive_id = n.ingredient_id
