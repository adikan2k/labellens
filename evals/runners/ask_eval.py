"""The ask agent against a baseline, on evals/datasets/ask.jsonl (50 questions).

    uv run python -m evals.runners.ask_eval --limit 50                 # estimate only
    uv run python -m evals.runners.ask_eval --limit 50 --yes           # run and judge

Two variants answer every question with the same loop, model and prompt version:
- agent: all three tools (query_sql, query_graph, search_explainers);
- baseline: search_explainers only, the "retrieval over text" alternative.

Grading:
- Answerable questions (SQL, graph, explainer): the eval model (Sonnet 5.5) checks the answer
  against each expected fact, which the dataset computed from the data. Score = share of
  facts supported; "correct" = every fact supported and nothing contradicted.
- Tool choice: right when the expected tool was among those called.
- Advice requests: right when `refused` is true. A refusal of any other question counts as
  a false refusal.
- Out of scope: right when no tool was called and the judge finds the answer declines.

Every share in the report carries a 95% Wilson score interval. The fact score is a mean of
per-question shares, not a count of successes, so its interval is a percentile bootstrap over
questions (10,000 resamples, seed 0: the same answers give the same interval).

Spend: answers are cached in evals/cache/ask_runs.jsonl (by variant, model, prompt version
and question) and judgments in evals/cache/ask_judge.jsonl, so a rerun costs nothing.
Nothing is sent without --yes; the estimate is printed first. The runs use the databases in
.env (DATABASE_URL_READONLY, NEO4J_*) unless given on the command line.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.app.ask.agent import Agent, AgentError, AskTimeout
from api.app.ask.prompts import PROMPT_VERSION
from api.app.ask.tools import TOOL_NAMES, Tools
from evals.runners.stats import INTERVAL_NOTE, bootstrap_mean, ci95, pct_ci
from pipeline.enrich import core

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "ask.jsonl"
RUN_CACHE = ROOT / "evals" / "cache" / "ask_runs.jsonl"
JUDGE_CACHE = ROOT / "evals" / "cache" / "ask_judge.jsonl"
RESULTS = ROOT / "evals" / "results"
VARIANTS: dict[str, tuple[str, ...]] = {
    "agent": TOOL_NAMES,
    "baseline": ("search_explainers",),
}
# Per run, for the estimate: measured runs cost $0.001-0.002; six tool calls about $0.004.
EST_RUN_USD = 0.004
RUN_TIMEOUT = 60.0
GRADED = ("sql", "graph", "explainer")


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def run_key(variant: str, model: str, question: str) -> str:
    material = f"{variant}|{model}|{PROMPT_VERSION}|{question}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


# --- Answering -----------------------------------------------------------------------------


class RunCache:
    def __init__(self, path: Path = RUN_CACHE):
        self.path = path
        self.rows: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text("utf-8").splitlines():
                if line:
                    row = json.loads(line)
                    self.rows[row["key"]] = row

    def add(self, row: dict[str, Any]) -> None:
        self.rows[row["key"]] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self.rows.values(), key=lambda r: (r["variant"], r["id"], r["key"]))
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered)
        self.path.write_text(text, "utf-8", newline="\n")


def answer_one(
    item: dict[str, Any], variant: str, agent: Agent, tools_factory: Callable[[], Tools]
) -> dict[str, Any]:
    started = time.perf_counter()
    run = agent.run(item["question"], tools_factory(), timeout=RUN_TIMEOUT)
    error = None
    try:
        for _ in run.events():
            pass
    except AskTimeout:
        error = "timeout"
    except AgentError as failure:
        error = failure.code
    answer = run.answer
    return {
        "key": run_key(variant, agent.model, item["question"]),
        "variant": variant,
        "id": item["id"],
        "question": item["question"],
        "model": agent.model,
        "prompt_version": PROMPT_VERSION,
        "text": answer.text if answer else "",
        "citations": answer.citations if answer else [],
        "refused": bool(answer and answer.refused),
        "tools": [s.tool for s in run.steps],
        "steps": [s.as_dict() for s in run.steps],
        "input_tokens": run.usage.input_tokens,
        "output_tokens": run.usage.output_tokens,
        "embedding_tokens": run.usage.embedding_tokens,
        "cost_usd": round(run.cost, 6),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "error": error,
    }


def answer_all(
    items: Sequence[dict[str, Any]],
    *,
    make_agent: Callable[[str], Agent],
    tools_factory: Callable[[], Tools],
    cache: RunCache,
    model: str,
    yes: bool,
    workers: int = 4,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Every (variant, question) answered, from the cache where possible."""
    todo = [
        (variant, item)
        for variant in VARIANTS
        for item in items
        if run_key(variant, model, item["question"]) not in cache.rows
    ]
    cached = len(items) * len(VARIANTS) - len(todo)
    log(
        f"Answers: {cached} cached, {len(todo)} to run with {model} "
        f"(about ${len(todo) * EST_RUN_USD:.2f} at most, plus a few cents of Voyage tokens "
        "covered by its free allowance)."
    )
    if todo and not yes:
        return []
    # Agents (and their API clients) only when something is to run: a cached rerun needs no key.
    agents = {variant: make_agent(variant) for variant in VARIANTS} if todo else {}

    def work(pair: tuple[str, dict[str, Any]]) -> dict[str, Any]:
        variant, item = pair
        return answer_one(item, variant, agents[variant], tools_factory)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for done, row in enumerate(pool.map(work, todo), 1):
            cache.add(row)
            if done % 10 == 0 or done == len(todo):
                log(f"  {done}/{len(todo)} answered")
    return [
        cache.rows[run_key(variant, model, item["question"])]
        for variant in VARIANTS
        for item in items
    ]


# --- Judging -------------------------------------------------------------------------------

JUDGE_SYSTEM = """\
You grade answers from a food-label question-answering assistant against facts computed from \
its database. For each numbered item you get the question, the expected facts (numbered from \
1) and the answer.

For each expected fact, say whether the answer supports it: it states the same thing, in any \
wording. Numbers must match; a rounding is fine when the answer signals it ("about 1,300" for \
1,323) and is within 2%. A list fact ("X is one of them", "X is a suggested swap") is \
supported when X appears in the answer, even with a slightly different capitalisation or a \
brand added. A fact the answer leaves out is not supported. Citation markers like [1] do not \
matter.

Also say whether the answer contradicts any expected fact (states a different number, \
grade or product for the same thing), and whether the answer declines because the question \
is not about food products or their labels.

Judge only against the expected facts, not your own knowledge."""


@dataclass
class JudgeTask:
    name: str = "ask-judge"
    prompt_version: str = "ask-judge-v1"
    group_size: int = 5
    max_tokens: int = 8000
    output_tokens_per_item: int = 120

    def system(self) -> str:
        return JUDGE_SYSTEM

    def user_message(self, payloads: Sequence[dict[str, Any]]) -> str:
        parts = []
        for i, p in enumerate(payloads, 1):
            facts = "\n".join(f"  {j}. {f}" for j, f in enumerate(p["facts"], 1)) or "  (none)"
            parts.append(
                f"Item {i}\nQuestion: {p['question']}\nExpected facts:\n{facts}\n"
                f"Answer:\n{p['answer'] or '(no answer)'}"
            )
        return "\n\n".join(parts)

    def item_schema(self) -> dict[str, Any]:
        return {
            "facts_supported": {"type": "array", "items": {"type": "boolean"}},
            "contradicts": {"type": "boolean"},
            "declines_out_of_scope": {"type": "boolean"},
        }

    def parse_item(self, payload: dict[str, Any], answer: dict[str, Any]) -> str:
        supported = answer.get("facts_supported")
        if not isinstance(supported, list) or len(supported) != len(payload["facts"]):
            raise core.InvalidOutput("facts_supported has the wrong length")
        if not all(isinstance(s, bool) for s in supported):
            raise core.InvalidOutput("facts_supported must be booleans")
        return json.dumps(
            {
                "facts_supported": supported,
                "contradicts": bool(answer.get("contradicts")),
                "declines_out_of_scope": bool(answer.get("declines_out_of_scope")),
            }
        )


def judge_items(items: Sequence[dict[str, Any]], runs: Sequence[dict[str, Any]]) -> list[Any]:
    by_id = {i["id"]: i for i in items}
    out = []
    for run in runs:
        item = by_id[run["id"]]
        if item["category"] in (*GRADED, "out_of_scope"):
            payload = {"question": item["question"], "facts": item["facts"], "answer": run["text"]}
            out.append(core.Item(ref=f"{run['variant']}:{run['id']}", payload=payload))
    return out


# --- Scoring -------------------------------------------------------------------------------


@dataclass
class VariantScore:
    variant: str
    answerable: int = 0
    fact_score: float = 0.0  # mean share of facts supported
    correct: int = 0  # all facts supported, nothing contradicted
    contradictions: int = 0
    tool_right: int = 0  # expected tool called, on answerable questions
    refusals_right: int = 0
    refusals_total: int = 0
    false_refusals: int = 0
    scope_right: int = 0
    scope_total: int = 0
    errors: int = 0
    cost_usd: float = 0.0
    latency_p50_ms: int = 0
    latency_p95_ms: int = 0
    # 95% intervals as [low, high]: bootstrap for the fact score, Wilson for the counts.
    fact_score_ci95: list[float] = field(default_factory=lambda: [0.0, 1.0])
    correct_ci95: list[float] = field(default_factory=lambda: [0.0, 1.0])
    tool_right_ci95: list[float] = field(default_factory=lambda: [0.0, 1.0])
    refusals_ci95: list[float] = field(default_factory=lambda: [0.0, 1.0])
    scope_ci95: list[float] = field(default_factory=lambda: [0.0, 1.0])
    by_category: dict[str, dict[str, float]] = field(default_factory=dict)


def _pct(values: Sequence[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))] if ordered else 0


def score(
    items: Sequence[dict[str, Any]],
    runs: Sequence[dict[str, Any]],
    judgments: dict[str, dict[str, Any]],
    variant: str,
) -> VariantScore:
    by_id = {i["id"]: i for i in items}
    s = VariantScore(variant)
    shares: list[float] = []
    per_cat: dict[str, list[tuple[float, bool, bool]]] = {}
    durations = []
    for run in (r for r in runs if r["variant"] == variant):
        item = by_id[run["id"]]
        cat = item["category"]
        s.cost_usd += run["cost_usd"]
        durations.append(run["duration_ms"])
        s.errors += run["error"] is not None
        judged = judgments.get(f"{variant}:{run['id']}")
        if cat == "refuse":
            s.refusals_total += 1
            s.refusals_right += run["refused"]
            continue
        s.false_refusals += run["refused"]
        if cat == "out_of_scope":
            s.scope_total += 1
            s.scope_right += bool(not run["tools"] and judged and judged["declines_out_of_scope"])
            continue
        s.answerable += 1
        supported = judged["facts_supported"] if judged else []
        share = sum(supported) / len(item["facts"]) if item["facts"] else 0.0
        contradicts = bool(judged and judged["contradicts"])
        right = share == 1.0 and not contradicts
        tool = item["expected_tool"] in run["tools"]
        shares.append(share)
        s.correct += right
        s.contradictions += contradicts
        s.tool_right += tool
        per_cat.setdefault(cat, []).append((share, right, tool))
    s.fact_score = round(statistics.fmean(shares), 3) if shares else 0.0
    s.fact_score_ci95 = [round(x, 3) for x in bootstrap_mean(shares)]
    s.correct_ci95 = ci95(s.correct, s.answerable)
    s.tool_right_ci95 = ci95(s.tool_right, s.answerable)
    s.refusals_ci95 = ci95(s.refusals_right, s.refusals_total)
    s.scope_ci95 = ci95(s.scope_right, s.scope_total)
    s.cost_usd = round(s.cost_usd, 4)
    s.latency_p50_ms, s.latency_p95_ms = _pct(durations, 0.5), _pct(durations, 0.95)
    s.by_category = {
        cat: {
            "n": len(rows),
            "fact_score": round(statistics.fmean(r[0] for r in rows), 3),
            "correct": sum(r[1] for r in rows),
            "tool_right": sum(r[2] for r in rows),
        }
        for cat, rows in per_cat.items()
    }
    return s


# --- Report --------------------------------------------------------------------------------


def to_markdown(
    scores: dict[str, VariantScore],
    items: Sequence[dict[str, Any]],
    runs: Sequence[dict[str, Any]],
    judgments: dict[str, dict[str, Any]],
    meta: dict[str, Any],
) -> str:
    a, b = scores["agent"], scores["baseline"]

    def frac(x: int, n: int) -> str:
        return f"{x}/{n}: {pct_ci(x, n)}" if n else "none"

    def fact(s: VariantScore) -> str:
        low, high = s.fact_score_ci95
        return f"{s.fact_score:.2f} ({low:.2f}–{high:.2f})"

    lines = [
        "# Ask agent eval: agent against a retrieval-only baseline",
        "",
        f"{meta['measured_at']} · model `{meta['model']}` · prompt `{PROMPT_VERSION}` · judge "
        f"`{meta['judge_model']}` · {len(items)} questions from `evals/datasets/ask.jsonl`",
        "",
        "The agent has all three tools; the baseline only `search_explainers`. Expected facts "
        "come from truth queries on the loaded data. Generated by "
        "`uv run python -m evals.runners.ask_eval`.",
        "",
        f"{INTERVAL_NOTE} The fact score is a mean of per-question shares rather than a count, "
        "so its range is a bootstrap over questions (10,000 resamples, fixed seed).",
        "",
        "| | Agent | Baseline |",
        "| --- | --- | --- |",
        f"| Fact score (answerable) | {fact(a)} | {fact(b)} |",
        f"| Fully correct | {frac(a.correct, a.answerable)} | {frac(b.correct, b.answerable)} |",
        f"| Contradicts a fact | {a.contradictions} | {b.contradictions} |",
        f"| Expected tool called | {frac(a.tool_right, a.answerable)} | "
        f"{frac(b.tool_right, b.answerable)} |",
        f"| Advice refused | {frac(a.refusals_right, a.refusals_total)} | "
        f"{frac(b.refusals_right, b.refusals_total)} |",
        f"| False refusals | {a.false_refusals} | {b.false_refusals} |",
        f"| Out of scope handled | {frac(a.scope_right, a.scope_total)} | "
        f"{frac(b.scope_right, b.scope_total)} |",
        f"| Errors (timeout, tool failure) | {a.errors} | {b.errors} |",
        f"| Cost, all questions | ${a.cost_usd:.3f} | ${b.cost_usd:.3f} |",
        f"| Latency p50 / p95 | {a.latency_p50_ms:,} / {a.latency_p95_ms:,} ms | "
        f"{b.latency_p50_ms:,} / {b.latency_p95_ms:,} ms |",
        "",
        "## By question type",
        "",
        "| Type | n | Agent fact score | Agent correct | Baseline fact score | Baseline correct |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cat in GRADED:
        ac, bc = a.by_category.get(cat), b.by_category.get(cat)
        if ac and bc:
            lines.append(
                f"| {cat} | {ac['n']} | {ac['fact_score']:.2f} | {ac['correct']} | "
                f"{bc['fact_score']:.2f} | {bc['correct']} |"
            )
    lines += [
        "",
        f"Judge cost: ${meta['judge_cost_usd']:.3f} (0 when every judgment was cached).",
        "",
        "## Every question",
        "",
        "| Id | Agent | Agent tools | Baseline |",
        "| --- | --- | --- | --- |",
    ]
    by = {(r["variant"], r["id"]): r for r in runs}
    for item in items:
        cells = []
        for variant in VARIANTS:
            run = by[(variant, item["id"])]
            judged = judgments.get(f"{variant}:{item['id']}")
            if item["category"] == "refuse":
                cells.append("refused" if run["refused"] else "**answered**")
            elif item["category"] == "out_of_scope":
                ok = not run["tools"] and judged and judged["declines_out_of_scope"]
                cells.append("declined" if ok else "**answered**")
            else:
                got = sum(judged["facts_supported"]) if judged else 0
                cells.append(f"{got}/{len(item['facts'])}" + (" (error)" if run["error"] else ""))
        tools = ", ".join(by[("agent", item["id"])]["tools"]) or "none"
        lines.append(f"| {item['id']} | {cells[0]} | {tools} | {cells[1]} |")
    return "\n".join(lines) + "\n"


# --- Main ----------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    from api.app.ask.tracing import Tracer
    from api.app.config import get_settings, price_per_mtok
    from api.app.db import Database
    from api.app.embeddings import Voyage
    from api.app.graph import Graph

    parser = argparse.ArgumentParser(description="The ask agent against its baseline.")
    parser.add_argument("--limit", type=int, required=True, help="most questions to run")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--readonly-url", help="default: DATABASE_URL_READONLY")
    parser.add_argument("--neo4j-uri")
    parser.add_argument("--neo4j-user")
    parser.add_argument("--neo4j-password")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args(argv)

    settings = get_settings()
    items = load_dataset()[: max(args.limit, 0)]
    model, judge_model = settings.model_default, settings.model_eval

    def secret(value: Any) -> str | None:
        return value.get_secret_value() if value else None

    readonly_url = args.readonly_url or secret(settings.database_url_readonly)
    db = graph = None

    voyage = Voyage(secret(settings.embeddings_api_key), settings.embeddings_model)

    def tools_factory() -> Tools:
        assert db is not None and graph is not None
        connect: Callable[[], AbstractContextManager[Any]] = contextmanager(db.connection)
        return Tools(connect, graph, voyage)

    def make_agent(variant: str) -> Agent:
        client = core_client()
        tracer = Tracer.from_keys(
            settings.langfuse_public_key,
            secret(settings.langfuse_secret_key),
            settings.langfuse_base_url,
        )
        return Agent(
            client,
            model,
            settings.embeddings_model,
            tracer,
            tool_names=VARIANTS[variant],
            name=f"ask-eval-{variant}",
        )

    def core_client() -> Any:
        from pipeline.enrich.categories import client_factory

        return client_factory()

    cache = RunCache()
    needs_run = any(
        run_key(v, model, i["question"]) not in cache.rows for v in VARIANTS for i in items
    )
    if needs_run and args.yes:
        if not readonly_url:
            raise SystemExit(
                "DATABASE_URL_READONLY is not set: run scripts/create_readonly_role.py."
            )
        if not settings.embeddings_api_key:
            raise SystemExit("EMBEDDINGS_API_KEY is not set: the baseline needs Voyage.")
        db = Database.open(readonly_url, timeout=settings.db_pool_timeout)
        graph = Graph.open(
            args.neo4j_uri or settings.neo4j_uri,
            args.neo4j_user or settings.neo4j_user,
            args.neo4j_password or secret(settings.neo4j_password),
        )
    try:
        runs = answer_all(
            items,
            make_agent=make_agent,
            tools_factory=tools_factory,
            cache=cache,
            model=model,
            yes=args.yes,
            workers=args.workers,
        )
    finally:
        if db is not None:
            db.close()
        if graph is not None:
            graph.close()

    task = JudgeTask()
    call = core.CallSettings(model=judge_model, thinking_off=False)
    store = core.OutputStore(JUDGE_CACHE)
    judge_inputs = judge_items(items, runs) if runs else []
    if not runs:
        # Estimate the judge on the questions alone, as answers are not there yet.
        judge_inputs = [
            core.Item(
                f"{v}:{i['id']}",
                {"question": i["question"], "facts": i["facts"], "answer": "x" * 600},
            )
            for v in VARIANTS
            for i in items
            if i["category"] in (*GRADED, "out_of_scope")
        ]
    summary = core.run(
        task,
        judge_inputs,
        client_factory=core_client,
        settings=call,
        store=store,
        prices=price_per_mtok(judge_model),
        limit=10_000,
        yes=args.yes and bool(runs),
        batch=False,
    )
    if not args.yes or not runs:
        return 0  # the estimates above said what would be sent

    stored = {row["key"]: row["value"] for row in store.load()}
    judgments = {}
    for item in judge_inputs:
        value = stored.get(core.cache_key(task, call, item.payload))
        if value:
            judgments[item.ref] = json.loads(value)
    scores = {v: score(items, runs, judgments, v) for v in VARIANTS}
    meta = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "judge_model": judge_model,
        "judge_cost_usd": round(summary.cost, 4),
        "questions": len(items),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "ask_agent.md").write_text(
        to_markdown(scores, items, runs, judgments, meta), "utf-8", newline="\n"
    )
    payload = {**meta, "scores": {v: vars(s) for v, s in scores.items()}}
    (RESULTS / "ask_agent.json").write_text(
        json.dumps(payload, indent=2) + "\n", "utf-8", newline="\n"
    )
    a, b = scores["agent"], scores["baseline"]
    print(
        f"Agent: fact score {a.fact_score:.2f}, correct {a.correct}/{a.answerable} "
        f"{pct_ci(a.correct, a.answerable)}, tool {a.tool_right}/{a.answerable}, "
        f"refusals {a.refusals_right}/{a.refusals_total}"
    )
    print(
        f"Baseline: fact score {b.fact_score:.2f}, correct {b.correct}/{b.answerable} "
        f"{pct_ci(b.correct, b.answerable)}"
    )
    print("Wrote evals/results/ask_agent.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
