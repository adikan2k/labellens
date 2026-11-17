{#
  Open Food Facts image folder for a barcode: codes of 8 digits or fewer are used as they are;
  9 to 12 digits are left-padded to 13; then the code is split 3/3/3/rest
  (0000159487776 -> 000/015/948/7776). Codes longer than 13 are split without padding:
  DuckDB's lpad truncates strings longer than the width, so it is only applied below 13.
#}
{% macro off_image_folder(code) -%}
  case
    when length({{ code }}) <= 8 then {{ code }}
    else regexp_replace(
        case when length({{ code }}) < 13 then lpad({{ code }}, 13, '0') else {{ code }} end,
        '^(\d{3})(\d{3})(\d{3})(\d+)$', '\1/\2/\3/\4'
    )
  end
{%- endmacro %}

{#
  The front image entry to show: front_en, then the product's own language, then any front_*,
  then a bare 'front'. Returns a struct with key and rev, or null.
#}
{% macro pick_front_image(images, lang) -%}
  coalesce(
    list_filter({{ images }}, lambda x: x.key = 'front_en' and x.rev is not null)[1],
    list_filter({{ images }}, lambda x: x.key = 'front_' || {{ lang }} and x.rev is not null)[1],
    list_filter({{ images }}, lambda x: starts_with(x.key, 'front_') and x.rev is not null)[1],
    list_filter({{ images }}, lambda x: x.key = 'front' and x.rev is not null)[1]
  )
{%- endmacro %}
