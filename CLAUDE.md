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
- API locally: `uv run fastapi dev api/app/main.py`
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
