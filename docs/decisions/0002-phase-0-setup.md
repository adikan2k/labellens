# 0002: Phase 0 setup choices

Status: accepted (draft for Aditya to rewrite) · Date: 2026-11-17 · Phase 0

## Repo outside OneDrive

**Chosen:** the repo lives in `C:\Users\adity\projects\labellens`, not in the OneDrive desktop folder.
**Why:** `food.parquet` is 8.05 GB, and `.venv` and `node_modules` hold tens of thousands of small files. OneDrive would try to upload all of it and can lock files during installs.
**Rejected:** keeping the repo in OneDrive and moving only the data out with an environment variable. Less safe, since the installs would still sync.

## One Python project at the root

**Chosen:** a single `pyproject.toml` and `uv.lock` for `pipeline/`, `api/`, `evals/` and `scripts/`, with Python pinned to 3.12.
**Why:** one environment, one lockfile, one pyright and ruff config. The API image can install a subset later if size matters.
**Rejected:** a uv workspace with a package per folder. Cleaner boundaries, but more config than a one-week build needs.

## One entry point for checks

**Chosen:** `scripts/check.py` runs every check, in parallel, and exits 2 on failure. CI calls it with `--only python` and `--only web`, and the Stop hook calls it with no flag.
**Why:** CI, the hook and a person at the terminal run exactly the same checks.
**Rejected:** separate commands in the CI file. They drift from what runs locally.

## Snapshot pinned to a dataset commit

**Chosen:** the downloader reads Hugging Face's `X-Repo-Commit` and downloads from that commit, resuming with HTTP Range. `manifest.json` records the commit and SHA-256. The finished file is read-only.
**Why:** the export is regenerated nightly. Pinning means a resumed download never mixes two revisions, and every number in `docs/data-profile.md` can be traced to exact bytes.
**Rejected:** `huggingface_hub` (an extra dependency for one file), and re-downloading from scratch on failure (8 GB at about 2.5 MB/s).

## Category taxonomy pulled forward from phase 3

**Chosen:** `dim_categories` is drafted from the profile and frozen in phase 0, before any hand labelling.
**Why:** the 200 hand labels are only useful if they use the same categories the model will predict in phase 3. Changing the taxonomy after labelling would void them.
**Rejected:** labelling with free text and mapping it later. That adds a mapping step that is itself a source of error.

## Labelling sample

**Chosen:** 200 US products with a non-empty name and ingredients, ordered by a hash of the barcode and a fixed seed. The labeller does not show Open Food Facts' own category.
**Why:** the hash order gives the same sample on any machine. Hiding the existing category keeps it from anchoring the gold labels, which are later used to grade the model.
**Rejected:** DuckDB's `USING SAMPLE` with a seed, which can vary with thread count and file layout.

## Web tokens enforced by Tailwind

**Chosen:** `globals.css` clears Tailwind's default colours, spacing, radii, shadows and type sizes, then defines only the DESIGN.md tokens.
**Why:** a class outside the design system has nothing to resolve to, so rule 5 holds without anyone policing it.
**Rejected:** keeping the defaults and relying on review.
