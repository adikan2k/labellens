# LabelLens: build spec

LabelLens turns the Open Food Facts database into a product people can search, question and plug into Claude. It ships as a tested data pipeline, a knowledge graph, a dashboard, a web app and an MCP App.

This file is what Claude Code builds against. Each phase has a scope and a "done when" line. A phase is not done until its "done when" is true and you have seen the evidence.

Sprint dates: phase 0 on Tue Nov 17, phases 1 and 2 on Wed Nov 18, phases 3 and 4 on Thu Nov 19, phases 5 and 6 on Fri Nov 20, design polish on Mon Nov 23, launch checks on Tue Nov 24.

---

## 1. Product

**For whom.** Shoppers who want to understand a product label, and engineers who want to see a real data and AI system end to end.

**What a visitor can do**

1. Search for a product by name, brand or barcode and see its label, explained.
2. See which additives and ingredients it contains, with a plain-English note on each.
3. Find better swaps in the same category.
4. Explore the US packaged-food landscape on a dashboard.
5. Ask a question in plain English ("cereals under 5 g sugar without artificial colours") and see the steps the agent took.
6. Use LabelLens from inside Claude through its MCP App.

**Out of scope.** Accounts, saved lists, user contributions back to Open Food Facts, image recognition, and any medical or dietary advice.

---

## 2. Data source and licence

- Source: the Open Food Facts Parquet export on Hugging Face, dataset `openfoodfacts/product-database`, file `food.parquet`. It is regenerated from the nightly dump. Data page: https://world.openfoodfacts.org/data
- Use the bulk file only. Do not crawl the live API; Open Food Facts says scraping through the API gets blocked.
- Licence: the database is under the Open Database License (ODbL), individual contents under the Database Contents License, product images under CC BY-SA.
- Obligations this creates:
  - Every page footer says "Contains data from Open Food Facts, available under the Open Database License", with links to https://world.openfoodfacts.org and https://opendatacommons.org/licenses/odbl/1-0/
  - Tables we publish that are derived from the database stay under the ODbL. The README states this.
  - Product images are linked from Open Food Facts, not re-hosted.
- Scope: products sold in the United States. Confirm the filter column and the row count in phase 0 before committing.

Do not guess column names. Phase 0 profiles the file and writes `docs/data-profile.md`; every later phase uses the names recorded there.

---

## 3. Architecture

```
food.parquet (Hugging Face)
   │
   ▼
pipeline/ingest ── snapshot to data/raw/<date>/ (gitignored)
   │
   ▼
pipeline/dbt (DuckDB) ── staging → marts, with data tests
   │
   ├─► pipeline/enrich ── Claude Batch API, cached by input hash
   │
   ▼
pipeline/load ──► Neon Postgres + pgvector   (search, product, stats, ask)
             └──► Neo4j AuraDB Free          (graph, swaps)
                      │
                      ▼
               api/ (FastAPI on Cloud Run) ── /mcp (MCP App)
                      │
                      ▼
               web/ (Next.js on Vercel)
```

Dagster orchestrates ingest → dbt → enrich → load. GitHub Actions runs CI on every pull request and the full pipeline weekly.

### Repo layout

```
labellens/
  CLAUDE.md
  .claude/settings.json
  .env.example
  docs/        SPEC.md, DESIGN.md, data-profile.md, decisions/, design/refs/
  pipeline/    ingest/, dbt/, enrich/, load/, dagster/
  api/         app/, tests/
  web/         Next.js app
  evals/       datasets/, runners/, results/
  scripts/     one-off tools (labeller, cost estimator)
```

### Stack

| Layer | Choice |
| --- | --- |
| Python | 3.12, managed with uv; ruff for lint and format; pyright for types; pytest |
| Pipeline | DuckDB, dbt-duckdb, Dagster |
| Serving database | Neon Postgres with pgvector. Free plan: 1 GB per project, compute suspends after 5 idle minutes |
| Graph | Neo4j AuraDB Free: 200,000 nodes, 400,000 relationships |
| API | FastAPI, deployed to Google Cloud Run |
| Web | Next.js (App Router), TypeScript, Tailwind, shadcn/ui primitives restyled to DESIGN.md, Motion, pnpm |
| Models | `claude-haiku-5-5` for enrichment and the live agent; `claude-sonnet-5-5` only for eval comparisons. Both names live in one config file |
| Embeddings | One embeddings API, chosen in phase 0 and recorded in a decision note. Model name lives in config |
| Tracing | Langfuse |
| Evals | pytest-based runners in `evals/`, results written to `evals/results/` as JSON and Markdown |

---

## 4. Accounts and keys (you, day 1)

Create these before phase 0 ends. Put every secret in `.env` (never committed) and in the deploy platforms' secret settings.

- [ ] GitHub repo `labellens`, public
- [ ] Anthropic API key, with a monthly spend limit of $15 set in the console
- [ ] Embeddings provider key (whichever phase 0 picks)
- [ ] Neon project
- [ ] Neo4j AuraDB Free instance (save the generated password; it is shown once)
- [ ] Google Cloud project with billing enabled and a budget alert at $5
- [ ] Vercel account linked to GitHub
- [ ] Langfuse cloud project
- [ ] Reference screenshots saved to `docs/design/refs/` (see DESIGN.md)
- [ ] 200 products hand-labelled with `scripts/label.py` (built in phase 0)

---

## 5. Data model

Names below are targets. Map them to real source columns using `docs/data-profile.md`.

**dbt marts (DuckDB)**

| Model | Grain | Key columns |
| --- | --- | --- |
| `dim_products` | one row per barcode | code, name, brand, category_main, nutriscore_grade, nova_group, image_url, completeness |
| `fct_nutrition` | one row per product | code, energy_kcal_100g, sugars_100g, salt_100g, fat_100g, saturated_fat_100g, fiber_100g, proteins_100g |
| `dim_additives` | one row per additive | additive_id (e.g. `en:e330`), name, explainer (filled by enrichment) |
| `bridge_product_additives` | product × additive | code, additive_id |
| `dim_ingredients` | one row per normalised ingredient | ingredient_id, name, explainer |
| `bridge_product_ingredients` | product × ingredient | code, ingredient_id, rank |
| `dim_categories` | one row per category in our taxonomy | category_id, name, parent_id |

**Required dbt tests (at least 30 in total)**

- `unique` and `not_null` on every primary key.
- `relationships` from every bridge table to its dimensions.
- `accepted_values` for nutriscore_grade (a to e) and nova_group (1 to 4), allowing nulls.
- Range tests: every per-100 g nutrient between 0 and 100; energy between 0 and 900 kcal.
- A completeness test that fails if more than an agreed share of products lack a name.
- Row-count bounds on `dim_products`, set from the phase 0 profile.

**Serving tables (Neon)** hold only what the API reads. Before loading, print the expected size and stop if it exceeds 800 MB, leaving headroom under the 1 GB cap.

**Graph (Neo4j)**

- Nodes: `Product`, `Brand`, `Category`, `Additive`, `Ingredient`.
- Relationships: `(:Product)-[:MADE_BY]->(:Brand)`, `(:Product)-[:IN]->(:Category)`, `(:Product)-[:CONTAINS]->(:Additive)`, `(:Product)-[:HAS_INGREDIENT]->(:Ingredient)`, `(:Category)-[:CHILD_OF]->(:Category)`.
- Subset: the most complete products, capped so the total stays under 180,000 nodes and 360,000 relationships. The loader prints counts and refuses to exceed them.

---

## 6. API contract

Fix this in phase 0 as an OpenAPI file so the web and API sessions can build in parallel.

| Method and path | Returns |
| --- | --- |
| `GET /health` | status and versions |
| `GET /search?q=&limit=` | products ranked by name, brand and barcode match |
| `GET /products/{code}` | full product: label fields, nutrition, additives with explainers, ingredients |
| `GET /products/{code}/swaps?limit=` | better products in the same category, with the reason each is better |
| `GET /stats/overview` | counts and distributions for the dashboard |
| `GET /graph/neighborhood?code=&depth=` | nodes and edges around a product for the explorer |
| `POST /ask` | server-sent events: each agent step, then the answer with citations |
| `/mcp` | MCP endpoint (streamable HTTP) |

Every response carries a `source` block naming the Open Food Facts snapshot date.

---

## 7. Phases

### Phase 0: setup (day 1)

- Move `claude-settings.json` to `.claude/settings.json` (it holds the deny rules for `.env` and raw data), then delete the original.
- Scaffold the layout above; add `uv`, `pnpm`, ruff, pyright, pytest and ESLint configs.
- GitHub Actions: lint, typecheck and test for Python and web on every pull request.
- `pipeline/ingest/profile.py`: read `food.parquet` with DuckDB, write `docs/data-profile.md` with every column, its type, its null rate, five sample values, the US filter column, and the US row count.
- `scripts/label.py`: a terminal labeller that samples 200 US products with a fixed seed, shows name, brand and ingredients, and records your chosen category from `dim_categories` into `evals/datasets/category_gold.csv`. It can stop and resume.
- `docs/openapi.yaml` for the contract in section 6.
- Pick the embeddings provider; write `docs/decisions/0001-embeddings.md`.
- `scripts/check.py`: runs ruff, pyright, pytest and the web lint, typecheck and tests; exits 2 on any failure and prints the failing output to stderr.
- Add a Stop hook to `.claude/settings.json` that runs `uv run python scripts/check.py`, so a session cannot end on a failing build. Add it only after the script passes on the empty app.

**Done when** CI is green on an empty app, `docs/data-profile.md` exists with real numbers, and the labeller runs.

### Phase 1: pipeline (day 2)

- Ingest snapshots the file to `data/raw/<date>/` and never edits it.
- dbt staging and marts as in section 5, with tests.
- Dagster assets for ingest, dbt and a run report.
- Run report `pipeline/reports/<date>.md`: row counts and null rates per mart.

**Done when** `dbt build` passes with at least 30 tests and the run report is committed.

### Phase 2: API, web app and dashboard (day 2)

- Load serving tables to Neon; add full-text search on name and brand.
- API endpoints: health, search, products, stats.
- Web pages: home with search, product page, dashboard, about page with method and attribution.
- Deploy API to Cloud Run and web to Vercel.

**Done when** a stranger can open the public URL, search for a common product, open it, and see the dashboard, with search answering in under 300 ms at the 95th percentile.

### Phase 3: enrichment and its eval (day 3)

- Fixed category taxonomy of 20 to 30 categories in `dim_categories`.
- Fill missing `category_main` with the model, using the Batch API. Output is validated with Pydantic; invalid output is retried once, then left null.
- One explainer per additive and per common ingredient, generated once each, not per product.
- Every call is cached by a hash of model, prompt version and input, so a rerun makes zero paid calls.
- Before any paid run, print the number of calls and the estimated cost, and require `--yes` to continue.
- Eval: compare model categories with your 200 labels. Report accuracy and a confusion table in `evals/results/`.

**Explainer rules.** Neutral and factual: what the substance is and why it is used. No health claims, no advice. Where Open Food Facts has taxonomy data for the additive, include it in the prompt and prefer it. The UI marks explainers as AI-generated.

**Done when** category accuracy on the 200 labels is reported and a second run of enrichment costs $0.

### Phase 4: food graph and swaps (day 3)

- Load the graph subset with counts checked against the caps.
- Swap finder: same category, better Nutri-Score grade, no additives on a flag list, ranked by Nutri-Score then fewest additives. Each swap carries a one-line reason built from the data, not from a model.
- Graph explorer page rendering `/graph/neighborhood` with a WebGL renderer.

**Done when** swaps appear on product pages and the explorer opens a product's neighbourhood in under a second.

### Phase 5: ask agent (day 4)

- A small tool-use loop on the Anthropic SDK, no framework. Three tools:
  1. `query_sql`: read-only Postgres role, allowlisted tables, a 3-second statement timeout, a forced `LIMIT 50`.
  2. `query_graph`: a fixed set of parameterised Cypher templates (swaps, products sharing an additive, category neighbours). No free-form Cypher.
  3. `search_explainers`: vector search over additive and ingredient explainers.
- At most 6 tool calls per question. Steps stream to the UI as they happen.
- Every answer cites the rows, nodes or explainers it used; the UI links each citation.
- Questions that ask for medical or dietary advice get a short refusal that points to the facts the app can show.
- Langfuse traces every run.
- Eval: 50 questions in `evals/datasets/ask.jsonl`, each with the expected answer facts and the expected tool. Report answer correctness and tool choice against a baseline that has only `search_explainers`.

**Done when** the eval report shows the agent against the baseline, and a question's steps are visible in the UI.

### Phase 6: MCP App (day 4)

- MCP server on the official Python SDK, stateless streamable HTTP per the MCP 2026-07-28 specification, mounted at `/mcp`.
- Tools: `search_products`, `get_product`, `find_swaps`, `explain_additive`.
- `get_product` and `find_swaps` declare a `ui://` resource under the MCP Apps extension (`io.modelcontextprotocol/ui`) that renders a compact product label card. Every tool also returns a plain-text result for clients without UI support.
- Public, read-only and unauthenticated by design; rate-limited per IP. Record the reasoning in a decision note.
- Eval: 30 natural requests in `evals/datasets/mcp.jsonl` with the expected tool and arguments. Runs in CI on changes to the server.

**Done when** the card renders inside Claude for a real product and the tool-selection eval passes 90% in CI.

---

## 8. Evals summary

| Eval | Dataset | Target |
| --- | --- | --- |
| Data tests | dbt | 30 or more, all passing |
| Category accuracy | 200 hand labels | 90% or better |
| Ask agent | 50 questions | Beats the single-tool baseline on correctness |
| MCP tool selection | 30 requests | 90% or better |
| Search latency | load test, 200 requests | 95th percentile under 300 ms |

Targets are goals. The README reports what was measured, including misses.

---

## 9. Cost guardrails

- Budget for model calls: about $10 for the whole project. Anthropic console limit at $15.
- No paid call runs in a loop without `--limit` and a printed cost estimate.
- Enrichment uses the Batch API and the cache.
- The public `/ask` endpoint: 10 questions per IP per hour, and a daily spend cap after which the UI serves cached example runs labelled as replays.
- Cloud Run: minimum instances 0, maximum 2.

---

## 10. Launch checklist

- [ ] Every target in section 8 measured and in the README
- [ ] Rate limit and daily cap triggered on purpose and behaved
- [ ] Works by keyboard, at 375 px wide, and with reduced motion
- [ ] ODbL attribution in the footer and on the about page
- [ ] Opened after an hour idle; cold start timed and noted
- [ ] Three cached example runs of `/ask` in place
- [ ] Decision log covers every phase
