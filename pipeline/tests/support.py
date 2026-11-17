"""Helpers shared by the test suites: run dbt on the fixture, reach the test Postgres."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = ROOT / "pipeline" / "dbt"
FIXTURE_RAW = ROOT / "pipeline" / "tests" / "fixtures" / "raw"
FIXTURE_PARQUET = FIXTURE_RAW / "2026-11-17" / "food.parquet"
# The fixture is small and deliberately over-represents unnamed products.
FIXTURE_VARS: dict[str, object] = {
    "raw_dir": "pipeline/tests/fixtures/raw",
    "min_products": 100,
    "max_products": 1000,
    "max_unnamed_share": 0.1,
}
# docker compose up -d postgres (see docker-compose.yml); CI sets TEST_DATABASE_URL.
DEFAULT_TEST_DATABASE_URL = "postgresql://labellens:labellens@localhost:54329/labellens"


def test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)


def _dbt_executable() -> str:
    found = shutil.which("dbt", path=str(Path(sys.executable).parent))
    assert found, "dbt is not installed in this environment (uv sync installs the pipeline group)"
    return found


@dataclass
class Run:
    returncode: int
    output: str
    results: list[dict[str, Any]]


@dataclass
class Build:
    run: Run
    db: Path
    tmp: Path


def run_dbt(command: str, tmp: Path, vars_: dict[str, object], *select: str) -> Run:
    """Run dbt as a person would, from the repo root, into tmp/fixture.duckdb."""
    target = tmp / f"target-{command}"
    args = [
        _dbt_executable(), command,
        "--project-dir", str(DBT_DIR),
        "--profiles-dir", str(DBT_DIR),
        "--target-path", str(target),
        "--log-path", str(tmp / "logs"),
        "--vars", json.dumps(vars_),
    ]  # fmt: skip
    if select:
        args += ["--select", *select]
    env = {
        **os.environ,
        "LABELLENS_DUCKDB": str(tmp / "fixture.duckdb"),
        "LABELLENS_DUCKDB_TMP": str(tmp / "spill"),
    }
    done = subprocess.run(
        args, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600, check=False,
    )  # fmt: skip
    results_file = target / "run_results.json"
    results = (
        json.loads(results_file.read_text("utf-8"))["results"] if results_file.exists() else []
    )
    return Run(done.returncode, done.stdout + done.stderr, results)
