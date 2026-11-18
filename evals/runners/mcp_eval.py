"""MCP tool selection: given only LabelLens's tool definitions, does a model pick the right tool
with the right arguments for what people actually ask?

Reads the tool definitions from the MCP server in-process (no database), then sends each
request in evals/datasets/mcp.jsonl to `model_default` (Haiku) with exactly those tools. The
real client in Claude is a larger model, so passing here is the stricter test. A request passes
when its first tool call is the expected tool with matching arguments (or, for off-topic
requests, when no tool is called):

- search_products: the query holds every expected word.
- get_product, find_swaps: the barcode, digits only; a 12-digit UPC equals its 13-digit EAN.
- explain_additive: the same additive by id or E-number (normalised as the server does), or
  one of its names.

Cached by model, tool-definition hash and request, so a rerun with unchanged tools costs $0.

    uv run python -m evals.runners.mcp_eval --limit 30            # estimate
    uv run python -m evals.runners.mcp_eval --limit 30 --yes --min-score 0.9
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.runners.stats import INTERVAL_NOTE, ci95, pct_ci

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "mcp.jsonl"
CACHE = ROOT / "evals" / "cache" / "mcp_runs.jsonl"
RESULTS = ROOT / "evals" / "results"
MAX_TOKENS = 400
CHARS_PER_TOKEN = 3.5
EST_OUTPUT_TOKENS = 120
TOOLS = ("search_products", "get_product", "find_swaps", "explain_additive")


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


# --- The tools, as the server publishes them ---------------------------------------------


def tool_definitions() -> tuple[list[dict[str, Any]], str]:
    """Anthropic tool definitions from the MCP server's tools/list, and its instructions."""
    import anyio
    from mcp import Client

    from api.app.db import Database
    from api.app.mcp.server import INSTRUCTIONS, create_mcp

    server = create_mcp(lambda: Database(pool=None), "https://labellens-beige.vercel.app").server

    async def listed() -> list[Any]:
        async with Client(server) as client:
            return (await client.list_tools()).tools

    tools = anyio.run(listed)
    defs = [
        {"name": t.name, "description": t.description or "", "input_schema": t.input_schema}
        for t in sorted(tools, key=lambda t: t.name)
    ]
    return defs, INSTRUCTIONS


def tools_hash(defs: list[dict[str, Any]], system: str) -> str:
    material = json.dumps({"tools": defs, "system": system}, sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


def run_key(model: str, thash: str, request: str) -> str:
    return hashlib.sha256(f"{model}|{thash}|{request}".encode()).hexdigest()[:32]


class RunCache:
    def __init__(self, path: Path = CACHE):
        self.path = path
        self.rows: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text("utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row

    def add(self, row: dict[str, Any]) -> None:
        self.rows[row["key"]] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self.rows.values(), key=lambda r: (r["model"], r["tools_hash"], r["id"]))
        text = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ordered)
        self.path.write_text(text, "utf-8", newline="\n")


# --- Asking --------------------------------------------------------------------------------


def ask(
    client: Any, model: str, system: str, defs: list[dict[str, Any]], request: str
) -> dict[str, Any]:
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=defs,
        tool_choice={"type": "auto"},
        thinking={"type": "disabled"},
        messages=[{"role": "user", "content": request}],
    )
    call = next((b for b in response.content if getattr(b, "type", "") == "tool_use"), None)
    return {
        "tool": call.name if call else None,
        "args": dict(call.input) if call else {},
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def estimate_usd(
    n: int, defs: list[dict[str, Any]], system: str, prices: tuple[float, float]
) -> float:
    prompt = len(json.dumps(defs)) + len(system) + 200
    tokens_in = prompt / CHARS_PER_TOKEN
    return n * (tokens_in * prices[0] + EST_OUTPUT_TOKENS * prices[1]) / 1e6


def answer_all(
    items: Sequence[dict[str, Any]],
    *,
    client_factory: Callable[[], Any],
    model: str,
    system: str,
    defs: list[dict[str, Any]],
    cache: RunCache,
    prices: tuple[float, float],
    yes: bool,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]] | None:
    """Every item's run, from the cache or the model. None when runs are missing and not --yes."""
    thash = tools_hash(defs, system)
    todo = [i for i in items if run_key(model, thash, i["request"]) not in cache.rows]
    log(
        f"{len(items) - len(todo)} cached, {len(todo)} to ask {model} "
        f"(tools {thash}; about ${estimate_usd(len(todo), defs, system, prices):.4f})."
    )
    if todo and not yes:
        log("Nothing sent. Add --yes to run it.")
        return None
    if todo:
        client = client_factory()
        for item in todo:
            started = time.perf_counter()
            run = ask(client, model, system, defs, item["request"])
            cache.add({
                "key": run_key(model, thash, item["request"]), "id": item["id"],
                "model": model, "tools_hash": thash, "request": item["request"], **run,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            })  # fmt: skip
    return [cache.rows[run_key(model, thash, i["request"])] for i in items]


# --- Scoring -------------------------------------------------------------------------------


def _digits(code: Any) -> str:
    digits = "".join(ch for ch in str(code) if ch.isdigit())
    return digits[1:] if len(digits) == 13 and digits.startswith("0") else digits


def args_match(tool: str, expected: dict[str, Any], args: dict[str, Any]) -> tuple[bool, str]:
    if tool == "search_products":
        query = str(args.get("query", "")).lower()
        missing = [w for w in expected["query_words"] if w not in query]
        return not missing, f"query {query!r}" + (f" lacks {missing}" if missing else "")
    if tool in ("get_product", "find_swaps"):
        got = str(args.get("code", ""))
        return _digits(got) == _digits(expected["code"]), f"code {got!r}"
    if tool == "explain_additive":
        from api.app.additives import normalise

        got = str(args.get("additive", ""))
        forms = normalise(got) or {}
        names = [n.lower() for n in expected["names"]]
        same = forms.get("id") == expected["additive_id"] or any(n in got.lower() for n in names)
        return same, f"additive {got!r}"
    return not args, "no arguments"


def score_item(item: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    tool_right = run["tool"] == item["tool"]
    if item["tool"] is None:
        why = "no tool, as expected" if tool_right else f"called {run['tool']}"
        return {"tool_right": tool_right, "args_right": tool_right, "passed": tool_right,
                "why": why}  # fmt: skip
    if not tool_right:
        return {"tool_right": False, "args_right": False, "passed": False,
                "why": f"called {run['tool'] or 'no tool'}"}  # fmt: skip
    ok, why = args_match(item["tool"], item["args"], run["args"])
    return {"tool_right": True, "args_right": ok, "passed": ok, "why": why}


def summarise(items: Sequence[dict[str, Any]], runs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    scored = [score_item(i, r) for i, r in zip(items, runs, strict=True)]
    by_tool: dict[str, dict[str, int]] = {}
    for item, s in zip(items, scored, strict=True):
        row = by_tool.setdefault(item["tool"] or "no tool", {"n": 0, "tool_right": 0, "passed": 0})
        row["n"] += 1
        row["tool_right"] += s["tool_right"]
        row["passed"] += s["passed"]
    n = len(items)
    passed = sum(s["passed"] for s in scored)
    tool_right = sum(s["tool_right"] for s in scored)
    return {
        "n": n,
        "passed": passed,
        "tool_right": tool_right,
        "score": passed / n if n else 0.0,
        "score_ci95": ci95(passed, n),
        "tool_score": tool_right / n if n else 0.0,
        "tool_score_ci95": ci95(tool_right, n),
        "by_tool": by_tool,
        "scored": scored,
        "input_tokens": sum(r["input_tokens"] for r in runs),
        "output_tokens": sum(r["output_tokens"] for r in runs),
    }


def to_markdown(
    summary: dict[str, Any],
    items: Sequence[dict[str, Any]],
    runs: Sequence[dict[str, Any]],
    meta: dict[str, Any],
) -> str:
    n, passed, tool_right = summary["n"], summary["passed"], summary["tool_right"]
    lines = [
        "# MCP tool selection",
        "",
        f"{meta['measured_at']} · model `{meta['model']}` · tools `{meta['tools_hash']}` · "
        f"{summary['n']} requests from `evals/datasets/mcp.jsonl` · cost ${meta['cost_usd']:.4f}",
        "",
        "Each request goes to the model with only LabelLens's MCP tool definitions. It passes "
        "when the first call is the expected tool with matching arguments, or no call for "
        "off-topic requests. Target: 90% (docs/SPEC.md). Generated by "
        "`uv run python -m evals.runners.mcp_eval`.",
        "",
        INTERVAL_NOTE,
        "",
        "| | Result |",
        "| --- | --- |",
        f"| Right tool and arguments | {passed}/{n}: {pct_ci(passed, n)} |",
        f"| Right tool | {tool_right}/{n}: {pct_ci(tool_right, n)} |",
        "",
        "| Expected tool | n | Right tool | Passed |",
        "| --- | --- | --- | --- |",
    ]
    for tool, row in summary["by_tool"].items():
        lines.append(f"| {tool} | {row['n']} | {row['tool_right']} | {row['passed']} |")
    lines += [
        "",
        "## Every request",
        "",
        "| Id | Request | Called | Result |",
        "| --- | --- | --- | --- |",
    ]
    for item, run, s in zip(items, runs, summary["scored"], strict=True):
        called = run["tool"] or "none"
        if run["args"]:
            called += " " + json.dumps(run["args"], ensure_ascii=False)
        mark = "pass" if s["passed"] else f"**fail**: {s['why']}"
        request = item["request"].replace("|", "\\|")
        lines.append(f"| {item['id']} | {request} | `{called}` | {mark} |")
    return "\n".join(lines) + "\n"


# --- Main ----------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    from api.app.config import get_settings, price_per_mtok
    from pipeline.enrich.categories import client_factory

    parser = argparse.ArgumentParser(description="MCP tool selection on 30 natural requests.")
    parser.add_argument("--limit", type=int, required=True, help="most requests to run")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--min-score", type=float, help="exit 1 below this share, e.g. 0.9")
    args = parser.parse_args(argv)

    model = get_settings().model_default
    prices = price_per_mtok(model)
    items = load_dataset()[: max(args.limit, 0)]
    defs, system = tool_definitions()
    runs = answer_all(items, client_factory=client_factory, model=model, system=system,
                      defs=defs, cache=RunCache(), prices=prices, yes=args.yes)  # fmt: skip
    if runs is None:
        return 0

    summary = summarise(items, runs)
    cost = (summary["input_tokens"] * prices[0] + summary["output_tokens"] * prices[1]) / 1e6
    meta = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "tools_hash": tools_hash(defs, system),
        "cost_usd": round(cost, 6),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "mcp_tools.md").write_text(
        to_markdown(summary, items, runs, meta), "utf-8", newline="\n"
    )
    payload = {**meta, **{k: v for k, v in summary.items() if k != "scored"}}
    (RESULTS / "mcp_tools.json").write_text(
        json.dumps(payload, indent=2) + "\n", "utf-8", newline="\n"
    )
    n, passed, tool_right = summary["n"], summary["passed"], summary["tool_right"]
    print(
        f"Tool and arguments right: {passed}/{n}, {pct_ci(passed, n)}; tool right: "
        f"{tool_right}/{n}, {pct_ci(tool_right, n)}. Wrote evals/results/mcp_tools.md"
    )
    for item, s in zip(items, summary["scored"], strict=True):
        if not s["passed"]:
            print(f"  fail {item['id']}: {s['why']}")
    if args.min_score is not None and summary["score"] < args.min_score:
        print(f"Below the {args.min_score:.0%} target.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
