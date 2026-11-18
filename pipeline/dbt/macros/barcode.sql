{#
  True when a code is a real GS1 barcode: GTIN-8, -12, -13 or -14, digits only, with a correct
  check digit. Counting from the right, after the check digit, digits weigh 3, 1, 3, 1, ...;
  the check digit makes the weighted sum a multiple of 10.

  Open Food Facts also holds codes that are not barcodes: restaurant menu items, shop-weighed
  goods and typos, 16 to 24 digits long. They stay searchable, but are not offered as swaps.
#}
{% macro gtin_valid(code) -%}
  coalesce(
    regexp_full_match({{ code }}, '[0-9]{8}|[0-9]{12,14}')
    and (
      10 - list_sum(list_transform(
        range(1, length({{ code }})),
        lambda i: try_cast(substr({{ code }}, length({{ code }}) - i, 1) as integer)
             * case when i % 2 = 1 then 3 else 1 end
      )) % 10
    ) % 10 = try_cast(right({{ code }}, 1) as integer),
    false
  )
{%- endmacro %}
