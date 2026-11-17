{#
  Where the raw files for this run live: var('snapshot_dir') if set, otherwise the newest
  folder under var('raw_dir') that holds a food.parquet. Paths are relative to the repo root.
#}
{% macro snapshot_dir() -%}
  {%- if var('snapshot_dir') -%}
    {{ return(var('snapshot_dir')) }}
  {%- endif -%}
  {%- if not execute -%}
    {{ return(var('raw_dir') ~ '/PARSE-TIME') }}
  {%- endif -%}
  {%- set sql -%}
    select max(parse_dirpath(file)) from glob('{{ var("raw_dir") }}/*/food.parquet')
  {%- endset -%}
  {%- set found = run_query(sql).columns[0].values()[0] -%}
  {%- if not found -%}
    {{ exceptions.raise_compiler_error("No snapshot under " ~ var('raw_dir') ~ ". Run pipeline.ingest.snapshot first.") }}
  {%- endif -%}
  {{ return(found | replace('\\', '/')) }}
{%- endmacro %}

{% macro food_parquet() -%}
  read_parquet('{{ snapshot_dir() }}/food.parquet')
{%- endmacro %}
