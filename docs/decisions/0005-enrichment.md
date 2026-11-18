# 0005: Enrichment with Claude (phase 3)

Status: draft for Aditya to rewrite. Numbers marked TBD are filled in after the paid runs.
Date: 2026-11-18. Phase 3.

## Fill every missing category, not a subset

**Chosen:** categorise all 676,320 named products that Open Food Facts' tags do not place (69% of the catalogue).
**Why:**
- Swaps (phase 4) need a category, and so do the dashboard's category panels.
- Claude Haiku 5.5 on the Batch API makes the full run cheap: the estimate is $3.89 for 604,507 distinct inputs.
**Rejected:**
- Only scanned products, or those with ingredients (about 150k): cheaper by about $3, but most products would get no swaps.
- Only the top 100k by search rank, for the same reason.

## The model's input is built in dbt

**Chosen:** `int_category_inputs` holds name, brand and the first 200 characters of ingredients for every named product. The fill and the eval both read it.
**Why:** the eval then measures exactly what production sends. The tag mapping moved to its own model (`int_product_tag_categories`), so `dim_products` can read the model's output without a cycle.

## "Other or unclear" over guessing

**Chosen:** the prompt tells the model to answer `other` when the name and ingredients don't say what the product is. The dashboard leaves `other` out of its category figures.
**Why:** a wrong category puts a product among the wrong swaps. An honest "unclear" costs less.

## Output files are the cache, and they are committed

**Chosen:** each item's cache key is a hash of task, model, prompt version, call settings and the exact input. Results live in `pipeline/enrich/outputs/`:
- `categories.parquet`, about 10 MB
- explainers as JSONL, readable in review

These files are both the cache and what dbt reads.
**Why:**
- A second run sends nothing and costs $0.
- The weekly GitHub build gets the results without paying.
- Every change to the model's output is a reviewable diff.
**Rejected:**
- A cache table in Neon: it eats into the 1 GB the serving tables need.
- A cloud bucket: another service and credential for a 10 MB file.

## Guards on spending

**Chosen:**
- Every paid command needs `--limit` and prints the estimated tokens and cost.
- It sends nothing without `--yes`.
- A submitted batch's id is saved, so an interrupted run collects that batch instead of submitting it again.
- Paid runs are CLI-only; Dagster and the weekly workflow never call the model.

## Validation, one retry, then null

**Chosen:**
- Categories must be one of the 26 leaf ids, enforced twice: structured outputs with an enum, then Pydantic.
- Explainers must be 40–320 characters, contain none of a list of health, safety and advice words, and not address the reader.
- A failing item is retried once in a new request. If it fails again it is stored as invalid (null), so it is not paid for twice.

## Explainers once per substance

**Chosen:** 520 additives plus the 500 most-used English ingredients that are not additives. An ingredient that is an additive reuses the additive's explainer.
**Why:** the top 500 ingredients cover 90% of ingredient appearances on US products, and 1,020 texts are few enough to read in review. Additive prompts carry Open Food Facts' taxonomy facts, which the model is told to prefer.

## Measured

- **Category accuracy** on 200 hand labels: TBD, with ingredients and name-only, against a 90% target. Tag-mapping baseline: TBD.
- **Haiku vs Sonnet 5.5** on the same labels: TBD.
- **Agreement with tags** on 1,000 tagged products: TBD.
- **Cost:** full fill TBD, explainers TBD. Second run: $0 (TBD, evidence).
