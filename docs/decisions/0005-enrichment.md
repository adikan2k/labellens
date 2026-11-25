# 0005: Enrichment with Claude (phase 3)

Status: accepted. Date: 2026-11-18. Phase 3.

## Fill every missing category, not a subset

**Chosen:** categorise all 676,320 named products that Open Food Facts' tags do not place (69% of the catalogue).
**Why:**
- Swaps (phase 4) need a category, and so do the dashboard's category panels.
- Claude Haiku 5.5 on the Batch API makes the full run cheap: it cost $5.18 for 604,507 distinct inputs.
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
- `categories.parquet`, 15 MB
- explainers as JSONL, readable in review

These files are both the cache and what dbt reads.
**Why:**
- A second run sends nothing and costs $0.
- The weekly GitHub build gets the results without paying.
- Every change to the model's output is a reviewable diff.
**Rejected:**
- A cache table in Neon: it eats into the 1 GB the serving tables need.
- A cloud bucket: another service and credential for a 15 MB file.

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

## Labels written by AI, said plainly

**Chosen:** the 200 eval labels were written by Claude Opus 5.5 from the category definitions, without seeing the evaluated model's answers. They live in `evals/datasets/category_silver_opus.csv`, and every report says who made them.
**Why:** labelling 200 unfamiliar products by hand was not a good use of time. I tried a blind 30-product check and stopped because I could not place most of the products, which is itself a sign of how hard these labels are.
**Cost of the choice:** the eval measures agreement with a stronger model, not accuracy against a person. `category_gold.csv` is still reserved for hand labels, and `scripts/audit_labels.py` runs the blind check if anyone does it later.

## Measured

| Run (labels by Claude Opus 5.5) | Accuracy | Cost |
| --- | ---: | ---: |
| Haiku 5.5, name, brand and ingredients | 90.0% (dev 88.6%, test 91.6%) | $0.0044 |
| Haiku 5.5, name and brand only | 87.5% | $0.0031 |
| Sonnet 5.5, name, brand and ingredients | 92.0% | $0.0872 |
| Open Food Facts' tag mapping, on the products it places | 87.5% | n/a |

- **Agreement with tags:** Haiku agrees with Open Food Facts' tags on 79.7% of 1,000 tagged products (name and brand only, $0.0154). Many disagreements are the tags' errors (chutney and jalapenos tagged as salted snacks) or gaps in `category_map` (`en:bacon` is not mapped).
- **Sonnet vs Haiku:** Sonnet is two points better at twenty times the price, about $78 for the fill instead of $3.89. The fill stays on Haiku.
- **Explainers:** 519 of 520 additives and 500 of 500 ingredients are valid, for $0.0201. E321 failed validation twice and is null.
- **Full fill:** 604,507 distinct inputs for 676,320 products, all valid. 98 failed validation once and passed on the retry. One batch of 12,091 requests finished in about 15 minutes. **Cost: $5.18**, 51.7M input and 10.4M output tokens.
- **The estimate missed:** it printed $3.89. It assumed 3 characters per token; the three real runs all came in at about 2. The estimator now uses 1.8 plus 100 tokens per request, which would have printed about $6.03, an upper bound as intended. A test pins the three measured runs.
- **Second run:** every enrichment command sends nothing and costs $0.00, even with `--yes`.
- **Result:** every named product has a category, 676,320 from the model and 308,940 from tags. The model put 32,178 (4.8%) in "Other or unclear" rather than guessing.
- **Total model spend in phase 3:** about $5.31 of the $100 API credit.
