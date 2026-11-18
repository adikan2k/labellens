"""Measure prompt caching on the ask agent: the same questions with and without it.

    uv run python -m scripts.measure_ask_caching --limit 10            # estimate only
    uv run python -m scripts.measure_ask_caching --limit 10 --yes      # run (costs money)

Takes the first --limit SQL questions of evals/datasets/ask.jsonl and runs each one twice
through the ask agent, one run at a time: once with cache_prompt off ("before") and once with
it on ("after"). The order alternates per question, so neither variant always meets the warmer
database. Per run it records cost, latency and the cache write and read tokens of every model
call. Results go to evals/results/ask_caching.json; a markdown table is printed.

"after" runs follow each other within the cache's 5-minute TTL, so after the first one they
read the cached prefix on their first call too. A cold run (the first in 5 minutes) writes the
prefix on its first call and reads it on the rest; the summary also prices every "after" run
as if it were cold, from its per-call usage.

The databases and keys come from the env file (--env-file, default .env): DATABASE_URL_READONLY,
NEO4J_*, ANTHROPIC_API_KEY and EMBEDDINGS_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any

from api.app.ask.agent import Agent
from api.app.ask.prompts import PROMPT_VERSION
from api.app.ask.tools import Tools
from api.app.config import CACHE_READ_MULTIPLIERS, CACHE_WRITE_MULTIPLIER, Settings, price_per_mtok
from evals.runners.ask_eval import EST_RUN_USD, load_dataset

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "evals" / "results" / "ask_caching.json"
RUN_TIMEOUT = 60.0


class RecordingClient:
    """Wraps anthropic.Anthropic: keeps each call's usage and latency."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **params: Any) -> Any:
        started = time.perf_counter()
        response = self.inner.messages.create(**params)
        usage = response.usage
        self.calls.append(
            {
                "ms": round((time.perf_counter() - started) * 1000),
                "input": usage.input_tokens,
                "cache_write": usage.cache_creation_input_tokens or 0,
                "cache_read": usage.cache_read_input_tokens or 0,
                "output": usage.output_tokens,
            }
        )
        return response


def run_one(agent: Agent, client: RecordingClient, item: dict[str, Any], tools: Tools) -> dict:
    client.calls = []
    started = time.perf_counter()
    run = agent.run(item["question"], tools, timeout=RUN_TIMEOUT)
    error = None
    try:
        for _ in run.events():
            pass
    except Exception as failure:  # recorded, not fatal: the comparison shows it
        error = type(failure).__name__
    return {
        "id": item["id"],
        "variant": "after" if agent.cache_prompt else "before",
        "ms": round((time.perf_counter() - started) * 1000),
        "cost_usd": run.cost,
        "model_calls": run.usage.model_calls,
        "input_tokens": run.usage.input_tokens,
        "cache_creation_input_tokens": run.usage.cache_creation_input_tokens,
        "cache_read_input_tokens": run.usage.cache_read_input_tokens,
        "output_tokens": run.usage.output_tokens,
        "calls": client.calls,
        "tools": [s.tool for s in run.steps],
        "text": run.answer.text if run.answer else "",
        "error": error,
    }


def cold_cost(row: dict[str, Any], model: str) -> float:
    """The run's cost had its first call written the prefix instead of reading it."""
    price_in, _ = price_per_mtok(model)
    read = row["calls"][0]["cache_read"] if row["calls"] else 0
    extra = read * (CACHE_WRITE_MULTIPLIER - CACHE_READ_MULTIPLIERS[model]) * price_in / 1e6
    return row["cost_usd"] + extra


def table(rows: list[dict[str, Any]], model: str) -> str:
    by = {(r["variant"], r["id"]): r for r in rows}
    ids = list(dict.fromkeys(r["id"] for r in rows))
    lines = [
        "| Question | Calls | Before $ | After $ | Before ms | After ms "
        "| Cache write | Cache read |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for qid in ids:
        b, a = by[("before", qid)], by[("after", qid)]
        lines.append(
            f"| {qid} | {b['model_calls']} / {a['model_calls']} | {b['cost_usd']:.6f} "
            f"| {a['cost_usd']:.6f} | {b['ms']:,} | {a['ms']:,} "
            f"| {a['cache_creation_input_tokens']:,} | {a['cache_read_input_tokens']:,} |"
        )
    summary = []
    for variant in ("before", "after"):
        vs = [r for r in rows if r["variant"] == variant]
        summary.append(
            f"- {variant}: total ${sum(r['cost_usd'] for r in vs):.6f}, "
            f"mean ${statistics.mean(r['cost_usd'] for r in vs):.6f} per run, "
            f"median {statistics.median(r['ms'] for r in vs):,.0f} ms, "
            f"mean {statistics.mean(r['ms'] for r in vs):,.0f} ms, "
            f"{sum(r['model_calls'] for r in vs)} model calls, "
            f"cache write {sum(r['cache_creation_input_tokens'] for r in vs):,}, "
            f"cache read {sum(r['cache_read_input_tokens'] for r in vs):,}"
        )
    after = [r for r in rows if r["variant"] == "after"]
    summary.append(
        f"- after, every run priced cold: total ${sum(cold_cost(r, model) for r in after):.6f}"
    )
    return "\n".join(lines) + "\n\n" + "\n".join(summary) + "\n"


def main(argv: list[str] | None = None) -> int:
    from api.app.ask.tracing import Tracer
    from api.app.db import Database
    from api.app.embeddings import Voyage
    from api.app.graph import Graph

    parser = argparse.ArgumentParser(description="Ask agent with and without prompt caching.")
    parser.add_argument("--limit", type=int, required=True, help="SQL questions to run")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args(argv)

    items = [i for i in load_dataset() if i["category"] == "sql"][: max(args.limit, 0)]
    runs = 2 * len(items)
    print(
        f"{len(items)} SQL questions x 2 variants = {runs} runs, one at a time. Estimate: about "
        f"${runs * 0.0015:.2f} (measured runs cost $0.001-0.002), "
        f"at most ${runs * EST_RUN_USD:.2f}."
    )
    if not args.yes:
        print("Nothing sent. Add --yes to run.")
        return 0

    settings = Settings(_env_file=args.env_file)  # pyright: ignore[reportCallIssue]

    def secret(value: Any) -> str | None:
        return value.get_secret_value() if value else None

    if settings.anthropic_api_key is None or settings.database_url_readonly is None:
        raise SystemExit("ANTHROPIC_API_KEY and DATABASE_URL_READONLY must be set. Nothing sent.")
    import anthropic

    client = RecordingClient(anthropic.Anthropic(api_key=secret(settings.anthropic_api_key)))
    model = settings.model_default
    agents = {
        flag: Agent(client, model, settings.embeddings_model, Tracer(), cache_prompt=flag)
        for flag in (False, True)
    }
    db = Database.open(secret(settings.database_url_readonly), timeout=settings.db_pool_timeout)
    graph = Graph.open(settings.neo4j_uri, settings.neo4j_user, secret(settings.neo4j_password))
    voyage = Voyage(secret(settings.embeddings_api_key), settings.embeddings_model)
    connect: Callable[[], AbstractContextManager[Any]] = contextmanager(db.connection)

    def tools() -> Tools:
        return Tools(connect, graph, voyage)

    rows: list[dict[str, Any]] = []
    try:
        with connect() as conn:  # wake the database before the first timed run
            conn.execute("select 1")
        for n, item in enumerate(items):
            order = (False, True) if n % 2 == 0 else (True, False)
            for flag in order:
                row = run_one(agents[flag], client, item, tools())
                rows.append(row)
                print(
                    f"  {item['id']} {row['variant']:6} ${row['cost_usd']:.6f} {row['ms']:>6,} ms "
                    f"write {row['cache_creation_input_tokens']:>5,} "
                    f"read {row['cache_read_input_tokens']:>5,} {row['error'] or ''}"
                )
    finally:
        db.close()
        graph.close()

    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "prompt_version": PROMPT_VERSION, "runs": rows}
    text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"
    RESULTS.write_text(text, "utf-8", newline="\n")
    print()
    print(table(rows, model))
    print(f"Wrote {RESULTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
