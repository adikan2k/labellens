{#
  The additive guide's lists stay within their caps and agree with the count: no more than
  five categories or six examples, examples never more than the products that list it, each
  category's count no more than the total, and an additive on a named product has an example.
#}
select additive_id
from {{ ref('agg_additive_usage') }}
where len(top_categories) > 5
   or len(example_codes) > 6
   or len(example_codes) > product_count
   or (product_count > 0 and len(example_codes) = 0)
   or list_max(list_transform(top_categories, lambda c: c.products)) > product_count
