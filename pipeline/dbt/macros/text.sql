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
  Words a label prints in capitals, in names that arrive lower-case:
  - a letter followed by digits takes a capital letter: b12 -> B12, d3 -> D3, e150a -> E150a;
  - a letter after a word that names its variant: vitamin e -> vitamin E,
    vitamins b and c -> vitamins B and C, acesulfame k -> acesulfame K,
    rebaudioside a -> rebaudioside A, patent blue v -> patent blue V, green s -> green S;
  - a short list of acronyms: DHA, EPA, MSG, BHA, BHT, TBHQ, EDTA, UHT.
  Everything else is left as it is.
#}
{% macro label_words(expr) -%}
  {%- set words = "string_split(" ~ expr ~ ", ' ')" -%}
  {%- set vitamin = "['vitamin', 'vitamins', 'vitamine', 'acesulfame', 'rebaudioside', 'blue', 'green']" -%}
  array_to_string(list_transform({{ words }}, lambda w, i: case
    when regexp_full_match(w, '[a-z][0-9]+[a-z]?') then upper(left(w, 1)) || substr(w, 2)
    when list_contains(['dha', 'epa', 'msg', 'bha', 'bht', 'tbhq', 'edta', 'uht'], w)
      then upper(w)
    when regexp_full_match(w, '[a-z]') and i > 1
      and list_contains({{ vitamin }}, lower({{ words }}[i - 1])) then upper(w)
    when regexp_full_match(w, '[a-z]') and i > 2 and lower({{ words }}[i - 1]) = 'and'
      and list_contains({{ vitamin }}, lower({{ words }}[i - 3])) then upper(w)
    else w
  end), ' ')
{%- endmacro %}

{#
  Display form of a name: first letter upper-case and label_words applied, the rest unchanged
  (DuckDB has no initcap, and initcap would be wrong for "Mono- and diglycerides").
  Open Food Facts writes chemical commas as U+201A so names never split on them
  (1‚2-hexanediol); they are turned back into commas here.
#}
{% macro capitalise(expr) -%}
  {%- set cased = label_words(expr) -%}
  replace(upper(left({{ cased }}, 1)) || substr({{ cased }}, 2), '‚', ',')
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
