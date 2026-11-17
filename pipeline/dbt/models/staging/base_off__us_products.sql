{{ config(materialized='table') }}

{#
  The only model that reads the 8 GB export. US products only (filter from docs/data-profile.md),
  one row per barcode, and only the columns later models use. A barcode that appears more than
  once keeps its most recently modified row, then the more complete one.
#}

with us as (
    select
        code,
        product_name,
        brands,
        lang,
        nutriscore_grade,
        nova_group,
        completeness,
        categories_tags,
        additives_tags,
        ingredients,
        nutriments,
        images,
        unique_scans_n,
        last_modified_t
    from {{ food_parquet() }}
    where {{ var('us_filter') }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by code
            order by last_modified_t desc nulls last, completeness desc nulls last
        ) as copy_rank,
        count(*) over (partition by code) as copies
    from us
)

select
    * exclude (copy_rank),
    '{{ snapshot_dir() }}' as snapshot_dir
from ranked
where copy_rank = 1
