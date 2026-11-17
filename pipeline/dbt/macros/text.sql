{#
  Text helpers for Open Food Facts' {lang, text} lists.
  pick_text follows the same rule as scripts/label.py: 'main', then 'en', then any non-blank.
#}

{% macro clean_text(expr) -%}
  nullif(
    trim(regexp_replace(
      replace(replace(replace(replace(replace(replace(
        {{ expr }},
        '&quot;', '"'), '&#39;', ''''), '&apos;', ''''), '&lt;', '<'), '&gt;', '>'), '&amp;', '&'),
      '\s+', ' ', 'g')),
    '')
{%- endmacro %}

{% macro pick_text(column) -%}
  {%- set nonblank = "list_filter(" ~ column ~ ", lambda x: trim(coalesce(x.text, '')) <> '')" -%}
  {{ clean_text(
      "coalesce(list_filter(" ~ nonblank ~ ", lambda x: x.lang = 'main')[1].text, "
      ~ "list_filter(" ~ nonblank ~ ", lambda x: x.lang = 'en')[1].text, "
      ~ nonblank ~ "[1].text)"
  ) }}
{%- endmacro %}
