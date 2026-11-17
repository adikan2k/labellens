# Test fixture

`raw/2026-11-17/` holds 284 real rows of Open Food Facts' `food.parquet` (every column) and the 121 `additives.json` entries they use. `dbt build` runs on it in CI and in `scripts/check.py`, so every model and test is exercised without the 8 GB file.

Rows are chosen by case: ordinary US products, products with categories, non-US products, duplicate barcodes, out-of-range nutrients, `unknown` and `not-applicable` Nutri-Score grades, products without a name, and additives missing from the taxonomy. The rows are the same on every rebuild:

```bash
uv run python scripts/make_fixture.py --snapshot data/raw/2026-11-17
```

Contains data from Open Food Facts, available under the Open Database License (https://opendatacommons.org/licenses/odbl/1-0/). This extract stays under the ODbL.
