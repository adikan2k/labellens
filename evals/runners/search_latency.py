"""Search latency eval: 200 requests to /search, end to end from this machine.

    uv run python -m evals.runners.search_latency --base-url https://<api>.run.app
    uv run python -m evals.runners.search_latency --base-url http://localhost:8000 --label local

Cycles through evals/datasets/search_queries.txt, one request at a time, and reports p50, p95
and p99 against the SPEC target (p95 under 300 ms). The first request is timed separately as
the cold start and is not in the percentiles. Results go to evals/results/ as JSON and Markdown,
whether or not the target is met. No paid calls.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUERIES = ROOT / "evals" / "datasets" / "search_queries.txt"
RESULTS = ROOT / "evals" / "results"
TARGET_P95_MS = 300.0


@dataclass
class Report:
    label: str
    base_url: str
    measured_at: str
    requests: int
    errors: int
    cold_first_ms: float
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    target_p95_ms: float
    meets_target: bool
    slowest: list[tuple[str, float]]


def load_queries(path: Path = QUERIES) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile: the smallest value with at least pct% of values at or below it."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceiling without floats drifting
    return ordered[int(rank) - 1]


def timed_get(url: str, timeout: float) -> tuple[float, int]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except (urllib.error.URLError, TimeoutError):
        status = 0
    return (time.perf_counter() - started) * 1000, status


def run(
    base_url: str, queries: list[str], requests: int, *, label: str, timeout: float = 15.0
) -> Report:
    base = base_url.rstrip("/")

    def url(q: str) -> str:
        return f"{base}/search?{urllib.parse.urlencode({'q': q, 'limit': 10})}"

    cold_ms, _ = timed_get(url(queries[0]), timeout)
    timings: list[tuple[str, float]] = []
    errors = 0
    for i in range(requests):
        q = queries[i % len(queries)]
        ms, status = timed_get(url(q), timeout)
        if status != 200:
            errors += 1
        timings.append((q, ms))

    values = [ms for _, ms in timings]
    p95 = percentile(values, 95)
    return Report(
        label=label,
        base_url=base,
        measured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        requests=requests,
        errors=errors,
        cold_first_ms=round(cold_ms, 1),
        p50_ms=round(statistics.median(values), 1),
        p95_ms=round(p95, 1),
        p99_ms=round(percentile(values, 99), 1),
        max_ms=round(max(values), 1),
        target_p95_ms=TARGET_P95_MS,
        meets_target=errors == 0 and p95 < TARGET_P95_MS,
        slowest=[(q, round(ms, 1)) for q, ms in sorted(timings, key=lambda t: -t[1])[:5]],
    )


def to_markdown(report: Report) -> str:
    verdict = "meets" if report.meets_target else "misses"
    rows = "\n".join(f"| `{q}` | {ms} |" for q, ms in report.slowest)
    return f"""# Search latency: {report.label}

Measured {report.measured_at} against `{report.base_url}`: {report.requests} sequential requests
to `/search` from `evals/datasets/search_queries.txt`, end to end from the client.

| | ms |
| --- | ---: |
| p50 | {report.p50_ms} |
| **p95** | **{report.p95_ms}** |
| p99 | {report.p99_ms} |
| max | {report.max_ms} |
| first request (cold, not in the percentiles) | {report.cold_first_ms} |

Errors: {report.errors}. Target: p95 under {report.target_p95_ms:.0f} ms. This run **{verdict}** it.

Slowest requests:

| Query | ms |
| --- | ---: |
{rows}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure /search latency.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--label", default="public", help="names the result files")
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    report = run(args.base_url, load_queries(), args.requests, label=args.label)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.out_dir / f"search_latency_{args.label}"
    stem.with_suffix(".json").write_text(json.dumps(asdict(report), indent=2) + "\n", "utf-8")
    stem.with_suffix(".md").write_text(to_markdown(report), "utf-8", newline="\n")
    print(to_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
