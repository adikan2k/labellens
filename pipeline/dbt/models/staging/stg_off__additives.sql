{{ config(materialized='view') }}

{#
  Open Food Facts' additives taxonomy (additives.json in the snapshot folder): one row per
  additive id with its English name and the facts phase 3's explainers draw on.
  Names are stored as 'E330 - Citric acid'; the E-number prefix is split off.
#}

with doc as (
    select content::json as j
    from read_text('{{ snapshot_dir() }}/additives.json')
),

entries as (
    select unnest(json_keys(j)) as additive_id, j
    from doc
),

fields as (
    select
        additive_id,
        j -> ('$."' || additive_id || '"') as e
    from entries
)

select
    additive_id,
    json_extract_string(e, '$.name.en') as name_raw,
    nullif(trim(regexp_replace(json_extract_string(e, '$.name.en'), '^E\s?\d+[a-z]*\s*-\s*', '', 'i')), '')
        as name,
    -- From the id, which keeps sub-variants apart (en:e322i -> E322i); the taxonomy's
    -- e_number field holds only the base number.
    nullif('E' || regexp_extract(additive_id, ':e(\d+[a-z]*)$', 1), 'E') as e_number,
    json_extract_string(e, '$.additives_classes.en') as classes,
    json_extract_string(e, '$.vegan.en') as vegan,
    json_extract_string(e, '$.vegetarian.en') as vegetarian,
    try_cast(json_extract_string(e, '$.efsa_evaluation_date.en') as date) as efsa_evaluation_date,
    json_extract_string(e, '$.wikidata.en') as wikidata_id,
    -- Open Food Facts' reading of EFSA's exposure data: 'high' where estimated intake can
    -- exceed the acceptable daily intake. Phase 4's swap rule excludes 'high'.
    nullif(replace(json_extract_string(e, '$.efsa_evaluation_overexposure_risk.en'), 'en:', ''), '')
        as overexposure_risk
from fields
