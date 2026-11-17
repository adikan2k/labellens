# LabelLens

LabelLens turns the Open Food Facts database into something you can search, question and plug into Claude: a tested data pipeline, a knowledge graph, a dashboard, a web app and an MCP App.

What gets built, phase by phase, is in [`docs/SPEC.md`](docs/SPEC.md). How it looks and moves is in [`docs/DESIGN.md`](docs/DESIGN.md).

## Layout

| Folder | What it holds |
| --- | --- |
| `pipeline/` | ingest, dbt models, enrichment, loaders, Dagster |
| `api/` | FastAPI service and its tests |
| `web/` | Next.js app |
| `evals/` | eval datasets, runners and results |
| `scripts/` | one-off tools (labeller, checks) |
| `docs/` | spec, design, data profile, decision notes |

## Commands

Requires [uv](https://docs.astral.sh/uv/), Node 22 and pnpm.

```bash
uv sync                                  # Python environment
pnpm -C web install                      # web dependencies
uv run python scripts/check.py           # every check: lint, types, tests, Python and web
uv run fastapi dev api/app/main.py       # API on http://localhost:8000
pnpm -C web dev                          # web on http://localhost:3000
```

Copy `.env.example` to `.env` and fill it in. `.env` is never committed.

## Data and licence

Contains data from [Open Food Facts](https://world.openfoodfacts.org), available under the [Open Database License (ODbL)](https://opendatacommons.org/licenses/odbl/1-0/). Individual contents are under the Database Contents License, and product images under CC BY-SA. Images are linked from Open Food Facts, not re-hosted.

Tables this project publishes that are derived from the Open Food Facts database (the dbt marts, the serving tables, the graph and the evaluation datasets built from them) remain under the ODbL.

Source: the `food.parquet` export of the Hugging Face dataset `openfoodfacts/product-database`. The bulk file is used; the live API is not crawled.
