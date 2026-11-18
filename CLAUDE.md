# LabelLens

Open Food Facts → tested pipeline → knowledge graph → web app, dashboard, ask agent and MCP App.

- What to build, phase by phase: `docs/SPEC.md`
- How it must look and move: `docs/DESIGN.md`
- Real column names in the source data: `docs/data-profile.md` (written in phase 0; never guess columns)

## Layout

`pipeline/` ingest, dbt, enrich, load, dagster · `api/` FastAPI · `web/` Next.js · `evals/` datasets, runners, results · `scripts/` one-off tools · `docs/` spec, design, decisions

## Commands

Phase 0 creates these. If one changes, update this list in the same commit.

- All checks (lint, types, tests, Python and web): `uv run python scripts/check.py`
- Python tests: `uv run pytest` · one file: `uv run pytest api/tests/test_search.py`
- Python lint and types: `uv run ruff check .` and `uv run pyright`
- dbt (run from the repo root; builds the newest snapshot under `data/raw/`): `uv run dbt build --project-dir pipeline/dbt --profiles-dir pipeline/dbt`
- Pipeline in Dagster: `uv run dagster dev -m pipeline.dagster.definitions` (set `DAGSTER_HOME` to keep run history)
- Run report after a build: `uv run python -m pipeline.report` (writes `pipeline/reports/<date>.md`)
- Rebuild the test fixture: `uv run python scripts/make_fixture.py`
- Local Postgres and Neo4j for tests and dev (Docker Desktop running): `docker compose up -d postgres neo4j neo4j-test` (tests use `neo4j-test`; `neo4j` holds the dev graph)
- Load the serving tables: `uv run python -m pipeline.load.serving --dry-run` (size only), then without `--dry-run` (reads `DATABASE_URL`; `--database-url postgresql://labellens:labellens@localhost:54329/labellens` for local)
- Load the graph into Neo4j: `uv run python -m pipeline.load.graph --dry-run` (counts against the caps), then without `--dry-run` (reads `NEO4J_*`; local dev graph: `bolt://localhost:57687`, user `neo4j`, password `labellens-local`); `--ping` keeps AuraDB Free awake
- API locally: `uv run fastapi dev api/app/main.py` (set `DATABASE_URL`, and `NEO4J_*` for the graph)
- Deploy the API: `uv run python scripts/deploy_api.py --project <id> --web-origin <vercel url>` prints the commands; add `--yes` to run them
- Production smoke test (read-only, no model calls; CI runs it every 6 hours and after each API deploy): `uv run python scripts/smoke.py` (`--api`, `--web` for other hosts; `--expect-unknown-404` once the web 404 page ships)
- Enrichment (paid; prints the estimate, sends only with `--yes`; reruns cost $0 from the committed outputs in `pipeline/enrich/outputs/`): `uv run python -m pipeline.enrich.categories --limit <n>` and `uv run python -m pipeline.enrich.explainers --limit <n>`, then `dbt build` again
- Explainer embeddings for the ask agent (Voyage; prints the estimate, sends only with `--yes`, resumes): `uv run python -m pipeline.enrich.embeddings --limit <n>`, then reload the serving tables
- Read-only database role for the ask agent's SQL tool (once per database; writes `DATABASE_URL_READONLY` to `.env` without printing it; `--rotate` for a new password): `uv run python scripts/create_readonly_role.py`
- Ask eval dataset (truth queries on the local Postgres and dev graph): `uv run python -m evals.datasets.build_ask`
- Ask eval, agent against the explainer-only baseline: `uv run python -m evals.runners.ask_eval --limit 50` (add `--yes`; cached per prompt version, so reruns cost $0)
- Replays served past the daily cap (the /ask page's example questions): `uv run python scripts/record_replays.py` (add `--yes`)
- MCP tool-selection eval (30 requests, target 90%; cached per tool definitions; CI runs it on server changes): `uv run python -m evals.runners.mcp_eval --limit 30` (add `--yes --min-score 0.9`)
- Preview the MCP label card without Claude (a local stand-in host on the local database): `uv run python scripts/card_preview.py --serve 8765`, then open http://localhost:8765
- MCP server: mounted on the API at `/mcp`; in Claude, add it as a custom connector with the API URL plus `/mcp` (no OAuth)
- Category eval (needs `evals/datasets/category_gold.csv`): `uv run python -m evals.runners.category_accuracy --limit 200` (add `--yes`; variants `--name-only`, `--model eval`, `--tagged-sample 1000`)
- Search latency eval: `uv run python -m evals.runners.search_latency --base-url <api url> --label public`
- Graph and swap latency eval: `uv run python -m evals.runners.graph_latency --base-url <api url> --label public`
- Lighthouse eval (needs Node and Chrome): `uv run python -m evals.runners.lighthouse --base-url https://labellens-beige.vercel.app`
- Regenerate web API types after changing `docs/openapi.yaml`: `pnpm -C web gen:api`
- Web: `pnpm -C web dev`, `pnpm -C web lint`, `pnpm -C web typecheck`, `pnpm -C web test`
- An eval: `uv run python -m evals.runners.<name>` (results go to `evals/results/`)
- Snapshot the source file: `uv run python -m pipeline.ingest.snapshot` (8 GB, resumable, into `data/raw/<date>/`, plus `additives.json`; `--taxonomy-only` adds just the taxonomy)
- Data profile: `uv run python -m pipeline.ingest.profile --us-filter "list_contains(countries_tags, 'en:united-states')"`
- Label the gold set: `uv run python scripts/label.py` (resumes; `u` undo, `q` quit)

## Environment

Variables are listed in `.env.example`. Never read `.env`. Neon and Neo4j credentials, API keys and model names come from environment variables or `api/app/config.py`, never from code.

## Rules

1. No paid model call runs in a loop without a `--limit` flag and a printed cost estimate. Enrichment also requires `--yes`.
2. Every feature ships with a test or an eval case.
3. Ask before adding a dependency.
4. Model names live only in config: `claude-haiku-5-5` by default, `claude-sonnet-5-5` for eval comparisons.
5. UI uses only the tokens in `docs/DESIGN.md`. A new token goes into that file first.
6. Every page footer keeps the Open Food Facts ODbL attribution.
7. Raw data under `data/raw/` is never edited and never committed.

## How we work

- Start each phase in plan mode against `docs/SPEC.md`. No code until the plan is approved.
- Small slices, one commit each, on a feature branch.
- Before calling something done, show evidence: the command you ran and its output, or a screenshot at 375, 1280 and 1600 px for UI work.
- After each phase, draft `docs/decisions/NNNN-<topic>.md` (what was chosen, what was rejected, why) for Aditya to rewrite in his own words.
