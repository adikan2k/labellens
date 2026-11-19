# 0003: Pipeline (phase 1)

Status: accepted · Date: 2026-11-17 · Phase 1

## One scan of the export, then views

**Chosen:** `base_off__us_products` is the only model that reads the 8 GB Parquet. It filters to US products, keeps one row per barcode and only the columns later models use. The other staging models are views over it; the marts are tables.
**Why:** a full build takes about a minute, and 33 seconds of that is the one scan.
**Rejected:** a staging table per concern, each scanning the file (several minutes per build); a dbt source with `external_location` (it can't find the newest snapshot folder on its own).

## Newest snapshot by default

**Chosen:** the `snapshot_dir()` macro asks DuckDB to `glob` `data/raw/*/food.parquet` and takes the newest folder, unless the `snapshot_dir` var pins one.
**Why:** the plain `dbt build` command in CLAUDE.md always builds the latest download, and a pinned rerun is one flag away.

## Bad values are blanked and counted, not dropped

**Chosen:** an impossible nutrient value (below 0, above 100 g, above 900 kcal) becomes null in `fct_nutrition`, and the product and its other values stay. Completeness scores above 1 (51 products) are capped at 1. `unknown` and `not-applicable` Nutri-Scores become null. The run report counts each of these.
**Why:** one typo shouldn't erase a product's good values, and nothing should vanish without a count.
**Rejected:** dropping the whole product's nutrition (loses good data); keeping the values and downgrading tests to warnings (the app would show impossible numbers).

## Duplicates keep the latest row

**Chosen:** a barcode listed twice keeps the row with the latest `last_modified_t`, then the higher completeness.
**Why:** the latest edit is the best guess at the current label. Only 3 US barcodes are affected.

## Categories: OFF tags first, the model later

**Chosen:** a seed maps 210 Open Food Facts category tags to our 26 categories, each with a priority: specific tags (2) beat umbrella tags (1), then the later tag wins. Ambiguous tags (`en:snacks`, `en:beverages`, `en:dairies`) are left out. This covers 310,440 products (76% of those with any tag); the other 692,329 wait for phase 3's model.
**Why:** OFF's own tags are free and mostly right, and the model then spends its budget only where tags are missing or ambiguous. Phase 3's eval can score the map against the 200 gold labels as a baseline.
**Rejected:** tag order alone (it filed pickles as salty snacks because `en:appetizers` is stored after `en:pickles`); sending every product to the model (cost, and it would ignore good data).

## Names worth showing

**Chosen:** ingredient names come from the most common spelling on English-language products, but only spellings that resemble the id (Jaro-Winkler at least 0.7); otherwise the name comes from the id. Additive ids use the taxonomy name. E-numbers come from the id, so variants stay apart (E322 and E322i).
**Why:** the first version named `en:chicken-fillet` "Kipfilet" (a Dutch label on a product marked English) and `en:e330` "E330". The product page and the explainers in phase 3 need real names.

## Additive names from a taxonomy snapshot

**Chosen:** Open Food Facts' static `additives.json` (920 KB) is saved beside each Parquet, with its own manifest and checksum.
**Why:** the Parquet holds additive ids only. One static file is not the live API, and it carries the taxonomy facts the phase 3 explainer prompts should use.

## Tests that need no package download

**Chosen:** 46 data tests, using dbt's four built-in tests plus four small generic tests written in the project (`in_range`, `unique_combination`, `max_null_share`, `row_count_between`).
**Why:** no `dbt deps` step in CI or the Stop hook, and each test is a few readable lines.
**Rejected:** dbt-utils and dbt-expectations (a package download, and more than we use).

## A committed fixture

**Chosen:** 284 real rows, cut by case (duplicates, impossible values, pseudo-grades, unnamed products, non-US rows, additives outside the taxonomy), committed under `pipeline/tests/fixtures/`. pytest runs the full `dbt build` and the full Dagster job on it.
**Why:** CI and the Stop hook exercise every model and test without the 8 GB file, and the fixture rebuilds to the same rows.

## Dagster wraps dbt, never downloads by surprise

**Chosen:** one asset per dbt model through dagster-dbt, with dbt tests as asset checks. `raw_snapshot` downloads only when its run config says so. dbt and Dagster sit in a `pipeline` dependency group.
**Why:** a scheduled or accidental run should never pull 8 GB, and the phase 2 API image can skip the pipeline packages.
**Deferred:** the weekly GitHub Actions run of the whole pipeline moves to phase 2, when the loaders give it something to publish.
