{#
  Rows from an enrichment output file in var('enrich_dir') (pipeline/enrich/outputs, written
  by pipeline/enrich and committed). A file that does not exist yet reads as no rows, so a
  fresh clone builds before any paid run. Columns: key, ref, value, status, model,
  prompt_version, all text.
#}
{% macro enrich_rows(filename) -%}
  {%- set path = var('enrich_dir') ~ '/' ~ filename -%}
  {%- set columns = ['key', 'ref', 'value', 'status', 'model', 'prompt_version'] -%}
  {%- set exists = false -%}
  {%- if execute -%}
    {%- set found = run_query("select count(*) from glob('" ~ path ~ "')").columns[0].values()[0] -%}
    {%- set exists = found > 0 -%}
  {%- endif -%}
  {%- if exists and filename.endswith('.parquet') -%}
    (select {{ columns | join(', ') }} from read_parquet('{{ path }}'))
  {%- elif exists -%}
    (select {{ columns | join(', ') }} from read_json('{{ path }}', format = 'newline_delimited',
      columns = { {%- for c in columns %}'{{ c }}': 'VARCHAR'{{ ', ' if not loop.last }}{% endfor -%} }))
  {%- else -%}
    (select {% for c in columns %}null::varchar as {{ c }}{{ ', ' if not loop.last }}{% endfor %} where false)
  {%- endif -%}
{%- endmacro %}
