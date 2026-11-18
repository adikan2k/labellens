"""Dagster code location: raw snapshot -> dbt models and tests -> run report.

    uv run dagster dev -m pipeline.dagster.definitions

Assets:
- raw_snapshot: the newest snapshot under data/raw. It downloads a new one (8 GB) only when
  run with config `download: true`, so nothing fetches the export by surprise.
- every dbt seed and model, one asset each, grouped as seeds, staging and marts; dbt's data
  tests are attached as asset checks. Models that read the raw files depend on raw_snapshot.
- run_report: pipeline/reports/<snapshot-date>.md from the build.

dbt runs with its working directory set to pipeline/dbt, so every path is passed absolute.
These environment variables override the defaults (the tests use them to run on the fixture):
LABELLENS_RAW_DIR, LABELLENS_ENRICH_DIR (enrichment outputs dbt reads), LABELLENS_DUCKDB,
LABELLENS_DUCKDB_TMP, LABELLENS_REPORTS_DIR, LABELLENS_DBT_TARGET (where dbt writes
run_results.json for the report), and LABELLENS_DBT_VARS (JSON merged into the dbt vars). A
run pointed elsewhere must override all of them, or it overwrites the real run's files.

Enrichment (pipeline/enrich) is not an asset: it costs money, so it runs only from its own
command with --limit and --yes. The build reads whatever enrichment outputs are committed.
"""

# No `from __future__ import annotations`: Dagster reads config classes from real annotations.
import json
import os
from collections.abc import Iterator, Mapping
from datetime import date
from pathlib import Path
from typing import Any

import dagster as dg
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from pipeline import report
from pipeline.ingest import snapshot as snap
from pipeline.ingest.profile import latest_snapshot

ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = ROOT / "pipeline" / "dbt"
RAW_DIR = Path(os.environ.get("LABELLENS_RAW_DIR", str(ROOT / "data" / "raw")))
ENRICH_DIR = Path(
    os.environ.get("LABELLENS_ENRICH_DIR", str(ROOT / "pipeline" / "enrich" / "outputs"))
)
DUCKDB_PATH = Path(
    os.environ.setdefault("LABELLENS_DUCKDB", str(ROOT / "data" / "labellens.duckdb"))
)
os.environ.setdefault("LABELLENS_DUCKDB_TMP", str(ROOT / "data" / "tmp"))
REPORTS_DIR = Path(os.environ.get("LABELLENS_REPORTS_DIR", str(report.REPORTS_DIR)))
RUN_TARGET = Path(os.environ.get("LABELLENS_DBT_TARGET", str(DBT_DIR / "target" / "dagster")))
DBT_VARS = {
    "raw_dir": RAW_DIR.as_posix(),
    "enrich_dir": ENRICH_DIR.as_posix(),
    **json.loads(os.environ.get("LABELLENS_DBT_VARS", "{}")),
}

RAW_SNAPSHOT = dg.AssetKey("raw_snapshot")
# Models that read the snapshot files directly (through the snapshot_dir() macro).
RAW_READERS = {"base_off__us_products", "stg_off__additives"}

dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR)
dbt_project.prepare_if_dev()
if not dbt_project.manifest_path.exists():
    dbt_project.preparer.prepare(dbt_project)


class SnapshotConfig(dg.Config):
    download: bool = False
    """Fetch today's snapshot (8 GB) and taxonomy if missing. Off by default."""


@dg.asset(key=RAW_SNAPSHOT, group_name="ingest", kinds={"parquet"})
def raw_snapshot(context: dg.AssetExecutionContext, config: SnapshotConfig) -> dg.MaterializeResult:
    """The Open Food Facts export and additives taxonomy the build reads."""
    if config.download:
        folder = RAW_DIR / date.today().isoformat()
        if not (folder / snap.FILE_NAME).exists():
            context.log.info(f"Downloading {snap.DEFAULT_URL} to {folder} (about 8 GB)")
            snap.snapshot(RAW_DIR, date.today())
        if not (folder / snap.ADDITIVES_FILE).exists():
            snap.snapshot_taxonomy(folder)

    folder = latest_snapshot(RAW_DIR).parent
    if not (folder / snap.ADDITIVES_FILE).exists():
        raise dg.Failure(
            f"{folder} has no additives.json. Run: uv run python -m pipeline.ingest.snapshot "
            f"--date {folder.name} --taxonomy-only"
        )
    manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
    return dg.MaterializeResult(
        metadata={
            "snapshot_date": manifest.get("snapshot_date", folder.name),
            "dataset_commit": manifest.get("dataset_commit"),
            "bytes": manifest.get("bytes"),
            "sha256": manifest.get("sha256"),
            "folder": dg.MetadataValue.path(str(folder)),
        }
    )


class LabelLensTranslator(DagsterDbtTranslator):
    """Groups dbt assets by folder and links raw-file readers to raw_snapshot."""

    def get_asset_spec(
        self, manifest: Mapping[str, Any], unique_id: str, project: DbtProject | None
    ) -> dg.AssetSpec:
        spec = super().get_asset_spec(manifest, unique_id, project)
        node = manifest["nodes"].get(unique_id) or manifest["sources"].get(unique_id) or {}
        fqn = node.get("fqn", [])
        group = (
            "seeds" if node.get("resource_type") == "seed" else (fqn[1] if len(fqn) > 2 else None)
        )
        if group:
            spec = spec.replace_attributes(group_name=group)
        if node.get("name") in RAW_READERS:
            spec = spec.merge_attributes(deps=[RAW_SNAPSHOT])
        return spec


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=LabelLensTranslator(),
)
def labellens_dbt(context: dg.AssetExecutionContext, dbt: DbtCliResource) -> Iterator[Any]:
    """dbt build: seeds, staging and marts, with every data test as an asset check."""
    args = ["build", "--vars", json.dumps(DBT_VARS)]
    yield from dbt.cli(args, context=context, target_path=RUN_TARGET).stream()


@dg.asset(group_name="report", deps=list(labellens_dbt.keys), kinds={"markdown"})
def run_report(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    """pipeline/reports/<snapshot-date>.md: row counts, null rates, tests and cleaning counts."""
    snapshot_date, text = report.build_report(DUCKDB_PATH, RUN_TARGET / "run_results.json")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{snapshot_date}.md"
    out.write_text(text, encoding="utf-8", newline="\n")
    context.log.info(f"Wrote {out}")
    return dg.MaterializeResult(
        metadata={"path": dg.MetadataValue.path(str(out)), "report": dg.MetadataValue.md(text)}
    )


@dg.asset(group_name="publish", deps=[run_report], kinds={"postgres"})
def serving_tables(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    """The API's tables in Postgres (Neon), loaded and swapped in by pipeline/load/serving.py.

    Only the `publish` job runs this, never `pipeline`, so building never writes to the live
    database by accident. It waits for the run report, so a failed build cannot publish.
    """
    from api.app.config import get_settings
    from pipeline.load import serving

    secret = get_settings().database_url
    if secret is None:
        raise dg.Failure("DATABASE_URL is not set; nothing to publish to.")
    sizes = serving.load(DUCKDB_PATH, secret.get_secret_value(), log=context.log.info)
    return dg.MaterializeResult(
        metadata={
            "database_mb": round(sizes["_database"] / 1e6, 1),
            "products_mb": round(sizes.get("products", 0) / 1e6, 1),
        }
    )


PUBLISH = dg.AssetSelection.assets(serving_tables)

pipeline_job = dg.define_asset_job(
    "pipeline",
    selection=dg.AssetSelection.all() - PUBLISH,
    description="Snapshot, dbt build, run report. Never writes to the live database.",
)
publish_job = dg.define_asset_job(
    "publish", selection=PUBLISH, description="Load the built marts into Postgres (Neon)."
)

defs = dg.Definitions(
    assets=[raw_snapshot, labellens_dbt, run_report, serving_tables],
    jobs=[pipeline_job, publish_job],
    resources={"dbt": DbtCliResource(project_dir=dbt_project)},
)
