{#
  Search rank for every named product, 1 first: products with a US/Canada barcode (GS1 prefix
  000-139) first, then English-language ones, then scans, then completeness. Scan counts are
  global, and imports tagged as sold in the US (Moroccan milk, French water) are often heavily
  scanned and recorded as English, so the barcode prefix keeps US products on top.

  One definition for the serving loader (search order) and the graph subset (which products
  the graph holds), so both agree.
#}

select
    code,
    row_number() over (
        order by
            (length(code) between 12 and 13
             and try_cast(left(lpad(code, 13, '0'), 3) as integer) between 0 and 139) desc,
            (lang = 'en') desc, scans desc, completeness desc nulls last, code
    )::integer as rank_pos
from {{ ref('dim_products') }}
where name is not null
