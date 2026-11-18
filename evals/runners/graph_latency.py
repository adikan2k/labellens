"""Graph and swap latency: does the explorer open a neighbourhood in under a second?

    uv run python -m evals.runners.graph_latency --base-url https://<api>.run.app --label public
    uv run python -m evals.runners.graph_latency --base-url http://localhost:8000 --label local

Picks products the graph holds (the API's own search for common words, keeping those whose
product says in_graph), then times GET /graph/neighborhood?depth=2 and GET
/products/{code}/swaps for each, one request at a time, end to end from this machine. The
first request of each kind is timed separately as the cold start. Reports p50, p95 and max
against the 1-second target (SPEC phase 4). Results go to evals/results/. No paid calls.
"""

from __future__ import annotations

import argparse
import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from evals.runners.search_latency import percentile, timed_get

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evals" / "results"
TARGET_MS = 1000.0
SEED_QUERIES = [
    "cereal", "cookies", "chips", "yogurt", "cheese", "pasta", "sauce", "bread", "juice",
    "chocolate", "crackers", "soup", "granola", "peanut butter", "ice cream", "salsa",
    "milk", "tea", "coffee", "beans",
]  # fmt: skip


@dataclass
class Timing:
    endpoint: str
    requests: int
    errors: int
    cold_first_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    meets_target: bool


@dataclass
class Report:
    label: str
    base_url: str
    measured_at: str
    products: int
    timings: list[Timing]
    target_ms: float = TARGET_MS


def _get_json(url: str, timeout: float = 15.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def graph_products(base: str, want: int) -> list[str]:
    """Barcodes of products the graph holds, found through the API itself."""
    codes: list[str] = []
    for q in SEED_QUERIES:
        url = f"{base}/search?{urllib.parse.urlencode({'q': q, 'limit': 20})}"
        for result in _get_json(url)["results"]:
            product = _get_json(f"{base}/products/{result['code']}")["product"]
            if product.get("in_graph") and result["code"] not in codes:
                codes.append(result["code"])
            if len(codes) >= want:
                return codes
    return codes


def time_endpoint(name: str, urls: list[str], timeout: float = 15.0) -> Timing:
    cold, _ = timed_get(urls[0], timeout)
    values, errors = [], 0
    for url in urls:
        ms, status = timed_get(url, timeout)
        values.append(ms)
        errors += status != 200
    p95 = percentile(values, 95)
    return Timing(
        endpoint=name,
        requests=len(values),
        errors=errors,
        cold_first_ms=round(cold, 1),
        p50_ms=round(percentile(values, 50), 1),
        p95_ms=round(p95, 1),
        max_ms=round(max(values), 1),
        meets_target=errors == 0 and p95 < TARGET_MS,
    )


def to_markdown(report: Report) -> str:
    rows = "\n".join(
        f"| `{t.endpoint}` | {t.p50_ms} | **{t.p95_ms}** | {t.max_ms} | {t.cold_first_ms} | "
        f"{t.errors} | {'meets' if t.meets_target else 'misses'} |"
        for t in report.timings
    )
    return f"""# Graph and swap latency: {report.label}

Measured {report.measured_at} against `{report.base_url}`: {report.products} products the
graph holds, one request at a time per endpoint, end to end from the client.

| Endpoint | p50 ms | p95 ms | max ms | first (cold) ms | errors | 1 s target |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
{rows}

The browser adds the layout and first frame on top (measured separately with a
`performance.mark("graph-rendered")`).
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Time the graph and swap endpoints.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--products", type=int, default=100)
    parser.add_argument("--label", default="public")
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    codes = graph_products(base, args.products)
    if not codes:
        raise SystemExit("Found no products the graph holds; is the graph loaded?")
    report = Report(
        label=args.label,
        base_url=base,
        measured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        products=len(codes),
        timings=[
            time_endpoint(
                "/graph/neighborhood?depth=2",
                [f"{base}/graph/neighborhood?code={c}&depth=2" for c in codes],
            ),
            time_endpoint("/products/{code}/swaps", [f"{base}/products/{c}/swaps" for c in codes]),
        ],
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.out_dir / f"graph_latency_{args.label}"
    stem.with_suffix(".json").write_text(json.dumps(asdict(report), indent=2) + "\n", "utf-8")
    text = to_markdown(report)
    stem.with_suffix(".md").write_text(text, "utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
