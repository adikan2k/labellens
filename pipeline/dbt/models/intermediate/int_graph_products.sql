{#
  The products the Neo4j graph holds: graded, named products with a real category, in search
  rank order, as many as fit under the relationship cap (var graph_max_relationships).

  Each product brings its own relationships: MADE_BY (if it has a brand), IN, one CONTAINS
  per additive and one HAS_INGREDIENT per recognised ingredient. The category tree adds a
  fixed number of CHILD_OF. So a running sum in rank order gives the exact cut-off. Nodes
  (products, their brands, ingredients and additives, categories) stay far below their cap;
  the loader checks both before writing.
#}

with candidates as (
    select
        r.code,
        r.rank_pos,
        (case when p.brand is not null then 1 else 0 end)
            + 1
            + coalesce(a.n, 0)
            + coalesce(i.n, 0) as relationships
    from {{ ref('int_product_rank') }} as r
    inner join {{ ref('dim_products') }} as p using (code)
    left join (
        select code, count(*) as n from {{ ref('bridge_product_additives') }} group by code
    ) as a using (code)
    left join (
        select code, count(*) as n from {{ ref('bridge_product_ingredients') }} group by code
    ) as i using (code)
    where p.nutriscore_grade is not null
      and p.category_main is not null
      and p.category_main <> 'other'
),

running as (
    select
        *,
        sum(relationships) over (order by rank_pos rows unbounded preceding) as cumulative
    from candidates
),

tree as (
    select count(*) as child_of from {{ ref('dim_categories') }} where parent_id is not null
)

select code, rank_pos, relationships
from running, tree
where cumulative + tree.child_of <= {{ var('graph_max_relationships') }}
