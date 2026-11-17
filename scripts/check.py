"""Run every check: ruff, pyright and pytest for Python; lint, typecheck and tests for web.

    uv run python scripts/check.py [--only python|web]

Prints one line per check. Output of failing checks goes to stderr. Exits 0 when everything
passes and 2 on any failure (exit 2 is what makes the Claude Code Stop hook block).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TextIO

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 600
Group = Literal["python", "web"]


@dataclass(frozen=True)
class Check:
    name: str
    group: Group
    cmd: tuple[str, ...]


@dataclass(frozen=True)
class Result:
    check: Check
    ok: bool
    seconds: float
    output: str


PY = sys.executable
CHECKS: tuple[Check, ...] = (
    Check("ruff check", "python", (PY, "-m", "ruff", "check", ".")),
    Check("ruff format", "python", (PY, "-m", "ruff", "format", "--check", ".")),
    Check("pyright", "python", (PY, "-m", "pyright")),
    Check("pytest", "python", (PY, "-m", "pytest")),
    Check("web lint", "web", ("pnpm", "-C", "web", "lint")),
    Check("web typecheck", "web", ("pnpm", "-C", "web", "typecheck")),
    Check("web test", "web", ("pnpm", "-C", "web", "test")),
)


def run_one(check: Check, cwd: Path = ROOT) -> Result:
    started = time.perf_counter()
    executable = shutil.which(check.cmd[0])
    if executable is None:
        return Result(check, False, 0.0, f"{check.cmd[0]} not found on PATH")
    try:
        completed = subprocess.run(
            [executable, *check.cmd[1:]],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return Result(check, False, TIMEOUT_SECONDS, f"timed out after {TIMEOUT_SECONDS}s")
    output = (completed.stdout + completed.stderr).strip()
    return Result(check, completed.returncode == 0, time.perf_counter() - started, output)


def run_checks(
    checks: Sequence[Check],
    *,
    cwd: Path = ROOT,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda c: run_one(c, cwd), checks))

    for result in results:
        mark = "pass" if result.ok else "FAIL"
        print(f"{mark}  {result.check.name:<14} {result.seconds:5.1f}s", file=out)

    failed = [r for r in results if not r.ok]
    for result in failed:
        print(f"\n===== {result.check.name} failed: {' '.join(result.check.cmd)}", file=err)
        print(result.output or "(no output)", file=err)

    if failed:
        print(f"\n{len(failed)} of {len(results)} checks failed.", file=out)
        return 2
    print(f"\nAll {len(results)} checks passed.", file=out)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run every lint, type and test check.")
    parser.add_argument("--only", choices=["python", "web"], help="run one group")
    args = parser.parse_args(argv)
    checks = [c for c in CHECKS if args.only is None or c.group == args.only]
    return run_checks(checks)


if __name__ == "__main__":
    raise SystemExit(main())
