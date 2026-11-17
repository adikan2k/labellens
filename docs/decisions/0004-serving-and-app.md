# 0004: Serving tables, API and web app (phase 2)

Status: accepted (draft for Aditya to rewrite) · Date: 2026-11-17 · Phase 2

## A compact serving table, not the marts as they are

**Chosen:** one wide `products` row per named product, with nutrition inline, additive and ingredient ids as ordered arrays, and the image stored as its path tail. Small lookup tables, one stats document, one meta table.
**Why:** loading the seven marts as they are (3.4 million ingredient bridge rows alone) lands near Neon's 1 GB cap. The compact layout is 348 MB with indexes for 985,260 products, and a product page is one query.
**Rejected:** bridge tables in Postgres (size, and joins on every product page); a document store (a second service for no gain).

## Guarded, atomic loads

**Chosen:** the loader estimates the size from DuckDB before connecting and stops above 800 MB. It builds in `serving_next` and swaps schemas in one transaction, with a lock timeout. It refuses if old plus new would pass 1 GB, unless `--replace`.
**Why:** Neon blocks writes past 1 GB, and readers should never see a half-loaded table. The estimate came in 20% above the actual size on the real data, as an upper bound should.

## Search: Postgres full-text, ranked once at load

**Chosen:** a GIN index over name and brand with the `english` configuration. The last word matches as a prefix (results while typing). Results are ordered by a precomputed `rank_pos`. Barcodes use prefix ranges on a C-collation primary key, and a 12-digit UPC also finds its 13-digit EAN.
**Why:** 1 to 16 ms in the database on the full data; no extra service. The prefix ranges replaced `LIKE ANY`, which Postgres would not serve from an index (30 ms scan, now 0.18 ms).
**Ranking:** products with a US/Canada barcode prefix (GS1 000 to 139) first, then English-language ones, then scans, then completeness. The first version ranked English-language products first, and the top results were Moroccan and French imports tagged as sold in the US. The barcode prefix fixed "milk" and "water" without changing searches that were already right.
**Rejected:** a search service (Typesense, Meilisearch), which means another deploy and bill; ranking by text relevance (`ts_rank` has to score every match, and "chocolate" matches 50,000 products).

## A sync API on a connection pool

**Chosen:** plain FastAPI endpoints on a psycopg connection pool: autocommit, no auto-prepared statements, schema named in every query.
**Why:** psycopg's async mode needs a selector event loop, which Windows does not use by default, so local development would break. Neon's pooled endpoint keeps no session state, which rules out `search_path` and prepared statements.

## The contract is checked from both sides

**Chosen:** the API's generated OpenAPI schema is compared with `docs/openapi.yaml` field by field in a test. The web's types are generated from the same file, and `pnpm typecheck` fails when they are stale.
**Why:** web and API were built against a file, and now neither can drift from it silently.

## Web: Cache Components, hand-built charts

**Chosen:** Next.js 16 with Cache Components. Server reads are `'use cache'` for hours, pages keep a prerendered shell, and dynamic product pages resolve their params inside Suspense. Live search runs in the browser against the API. Dashboard bars are built from the design tokens.
**Why:** the shell is served instantly from the CDN, and Neon only wakes for data. A chart library would bring its own colours and type, which DESIGN.md does not allow.
**Rejected:** shadcn/ui for these pages (no dialog, menu or popover yet); a chart library.

## Design fixes found by checking

White text on the Nutri-Score D and E chips fails WCAG AA (2.7:1 and 4.2:1), so D and E use black (7.8:1 and 5.1:1). A test recomputes every ratio from the tokens and checks DESIGN.md quotes them.

## Deploy

**Chosen:** the API on Cloud Run in `us-east4` (near Neon's `us-east-1`), minimum 0 and maximum 2 instances, `DATABASE_URL` from Secret Manager, Artifact Registry keeping the two newest images. The web is on Vercel. `scripts/deploy_api.py` prints every command and runs them only with `--yes`.
**Why:** both stay inside free tiers at demo traffic. The spend guardrails are in the commands themselves, and tests pin them. A $5 monthly spend cap on Cloud Run in the project backs them up.
**Measured:** 200 searches from a home connection to the public API: p50 102 ms, p95 193 ms, p99 302 ms, no errors (`evals/results/search_latency_public.md`).
**Considered when billing was blocked:** running the API as Vercel Python functions. It works, but Vercel's builder runs `uv sync --no-dev`, which still installs the `pipeline` group (Dagster, dbt, DuckDB) unless `UV_NO_DEFAULT_GROUPS=1` is set on the project. Cloud Run kept the tested container and a pool that stays open while an instance is warm.

## Weekly pipeline

**Chosen:** a GitHub Actions workflow that snapshots, builds, reports and loads into Neon weekly. In Dagster, publishing is a separate job from building.
**Why:** a build can run any time without touching the live site, and a failed build cannot publish.
