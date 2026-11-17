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

{#
  Display form of a name: first letter upper-case, the rest unchanged (DuckDB has no initcap).
  Open Food Facts writes chemical commas as U+201A so names never split on them
  (1‚2-hexanediol); they are turned back into commas here.
#}
{% macro capitalise(expr) -%}
  replace(upper(left({{ expr }}, 1)) || substr({{ expr }}, 2), '‚', ',')
{%- endmacro %}

{# Readable name from a taxonomy id: 'en:sea-salt' -> 'Sea salt'. #}
{% macro name_from_id(id_expr) -%}
  {{ capitalise("replace(split_part(" ~ id_expr ~ ", ':', 2), '-', ' ')") }}
{%- endmacro %}

{% macro pick_text(column) -%}
  {%- set nonblank = "list_filter(" ~ column ~ ", lambda x: trim(coalesce(x.text, '')) <> '')" -%}
  {{ clean_text(
      "coalesce(list_filter(" ~ nonblank ~ ", lambda x: x.lang = 'main')[1].text, "
      ~ "list_filter(" ~ nonblank ~ ", lambda x: x.lang = 'en')[1].text, "
      ~ nonblank ~ "[1].text)"
  ) }}
{%- endmacro %}
