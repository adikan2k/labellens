"""The Dagster code location loads and materialises every asset on the fixture.

Runs in a subprocess because pipeline/dagster/definitions.py reads its paths from the
environment at import; that keeps the fixture paths out of this test session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_RAW = ROOT / "pipeline" / "tests" / "fixtures" / "raw"

SCRIPT = r"""
import json
import dagster as dg
from pipeline.dagster.definitions import defs, labellens_dbt, raw_snapshot, run_report

graph = defs.get_repository_def().asset_graph
keys = {k.to_user_string() for k in graph.get_all_asset_keys()}
result = dg.materialize(
    [raw_snapshot, labellens_dbt, run_report],
    resources=defs.resources,
    raise_on_error=False,
)
checks = result.get_asset_check_evaluations()
base = graph.get(dg.AssetKey("base_off__us_products"))
events = result.get_asset_materialization_events()
print("RESULT " + json.dumps({
    "keys": sorted(keys),
    "groups": sorted({graph.get(k).group_name for k in graph.get_all_asset_keys()}),
    "base_deps": [k.to_user_string() for k in base.parent_keys],
    "success": result.success,
    "materialized": sorted(e.asset_key.to_user_string() for e in events),
    "checks": len(checks),
    "checks_passed": sum(1 for c in checks if c.passed),
}))
"""


def test_definitions_load_and_materialise_on_the_fixture(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "LABELLENS_RAW_DIR": str(FIXTURE_RAW),
        "LABELLENS_DUCKDB": str(tmp_path / "fixture.duckdb"),
        "LABELLENS_DUCKDB_TMP": str(tmp_path / "spill"),
        "LABELLENS_REPORTS_DIR": str(tmp_path / "reports"),
        "LABELLENS_DBT_VARS": json.dumps(
            {"min_products": 100, "max_products": 1000, "max_unnamed_share": 0.1}
        ),
        "DAGSTER_HOME": str(tmp_path / "dagster_home"),
    }
    (tmp_path / "dagster_home").mkdir()
    done = subprocess.run(
        [sys.executable, "-c", SCRIPT],
        cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600, check=False,
    )  # fmt: skip
    lines = [line for line in done.stdout.splitlines() if line.startswith("RESULT ")]
    assert lines, (done.stdout + done.stderr)[-4000:]
    out = json.loads(lines[-1].removeprefix("RESULT "))

    assert {"raw_snapshot", "run_report", "dim_products", "fct_nutrition"} <= set(out["keys"])
    assert out["groups"] == ["ingest", "marts", "report", "seeds", "staging"]
    assert out["base_deps"] == ["raw_snapshot"]
    assert out["success"], (done.stdout + done.stderr)[-4000:]
    assert set(out["materialized"]) == set(out["keys"])
    assert out["checks"] >= 30
    assert out["checks_passed"] == out["checks"]

    report = (tmp_path / "reports" / "2026-11-17.md").read_text("utf-8")
    assert report.startswith("# Pipeline run report: 2026-11-17")
    assert "Not passing" not in report
