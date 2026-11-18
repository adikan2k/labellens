"""The MCP tool-selection eval: dataset, the tools it reads, scoring, caching and the report."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from api.tests.scripted_client import ScriptedClient, text, tool_calls
from evals.runners import mcp_eval as ev

PRICES = (0.10, 0.50)


def test_the_dataset_has_the_planned_mix() -> None:
    items = ev.load_dataset()
    assert len(items) == 30 and len({i["id"] for i in items}) == 30
    assert Counter(i["tool"] for i in items) == {
        "search_products": 8, "get_product": 8, "find_swaps": 7,
        "explain_additive": 5, None: 2,
    }  # fmt: skip
    for item in items:
        assert item["tool"] in (*ev.TOOLS, None), item["id"]
        assert bool(item["args"]) == (item["tool"] is not None), item["id"]


def test_the_tools_come_from_the_server_with_its_instructions() -> None:
    defs, system = ev.tool_definitions()
    assert [d["name"] for d in defs] == sorted(ev.TOOLS)
    for d in defs:
        assert d["input_schema"]["type"] == "object" and d["description"], d["name"]
    assert "find_swaps directly" in system
    assert ev.tools_hash(defs, system) == ev.tools_hash(defs, system)
    assert ev.tools_hash(defs, system) != ev.tools_hash(defs, system + " ")


def test_arguments_match_as_people_and_models_write_them() -> None:
    words = {"query_words": ["honey", "nut", "cheerios"]}
    assert ev.args_match("search_products", words, {"query": "Honey Nut Cheerios cereal"})[0]
    assert not ev.args_match("search_products", words, {"query": "cheerios"})[0]
    code = {"code": "0044000031114"}
    for got in ("0044000031114", "044000031114", "0044 0000 31114"):
        assert ev.args_match("get_product", code, {"code": got})[0], got
    assert not ev.args_match("find_swaps", code, {"code": "0044000031115"})[0]
    e471 = {"additive_id": "en:e471", "names": ["mono- and diglycerides of fatty acids"]}
    for got in ("E471", "e 471", "en:e471", "Mono- and diglycerides of fatty acids"):
        assert ev.args_match("explain_additive", e471, {"additive": got})[0], got
    msg = {"additive_id": "en:e621", "names": ["monosodium glutamate"]}
    assert ev.args_match("explain_additive", msg, {"additive": "MSG"})[0]
    assert not ev.args_match("explain_additive", e471, {"additive": "E472"})[0]


def _item(tool: str | None, args: dict[str, Any] | None = None, n: int = 1) -> dict[str, Any]:
    return {"id": f"x-{n}", "request": f"request {n}", "tool": tool, "args": args or {}}


def _run(tool: str | None, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"tool": tool, "args": args or {}, "input_tokens": 1000, "output_tokens": 50}


def test_scoring_needs_the_tool_and_its_arguments() -> None:
    items = [
        _item("get_product", {"code": "0016000123991"}, 1),
        _item("get_product", {"code": "0016000123991"}, 2),
        _item("find_swaps", {"code": "0016000123991"}, 3),
        _item(None, n=4),
        _item(None, n=5),
    ]
    runs = [
        _run("get_product", {"code": "016000123991"}),  # 12-digit UPC: same product
        _run("get_product", {"code": "0016000123992"}),  # wrong barcode
        _run("get_product", {"code": "0016000123991"}),  # wrong tool
        _run(None),  # off-topic, no tool: right
        _run("search_products", {"query": "capital"}),
    ]
    summary = ev.summarise(items, runs)
    assert [s["passed"] for s in summary["scored"]] == [True, False, False, True, False]
    assert summary["score"] == 0.4 and summary["tool_score"] == 0.6
    assert summary["by_tool"]["get_product"] == {"n": 2, "tool_right": 2, "passed": 1}
    report = ev.to_markdown(summary, items, runs, {
        "measured_at": "2026-11-18T12:00:00+00:00", "model": "claude-haiku-5-5",
        "tools_hash": "abc", "cost_usd": 0.001,
    })  # fmt: skip
    assert summary["score_ci95"] == [0.1176, 0.7693]
    assert "| Right tool and arguments | 2/5: 40% (12–77%) |" in report
    assert "| Right tool | 3/5: 60% (23–88%) |" in report
    assert "95% confidence intervals (Wilson score)" in report
    assert "| x-3 | request 3 | `get_product" in report and "**fail**: called get_product" in report


def test_runs_are_estimated_then_cached(tmp_path: Path) -> None:
    items = [_item("get_product", {"code": "1"}, 1), _item(None, n=2)]
    defs = [{"name": "get_product", "description": "d", "input_schema": {"type": "object"}}]
    client = ScriptedClient(tool_calls(("get_product", {"code": "1"})), text("Canberra."))
    lines: list[str] = []
    kwargs: dict[str, Any] = {"client_factory": lambda: client, "model": "claude-haiku-5-5",
                              "system": "s", "defs": defs, "prices": PRICES,
                              "log": lines.append}  # fmt: skip

    cache = ev.RunCache(tmp_path / "runs.jsonl")
    assert ev.answer_all(items, cache=cache, yes=False, **kwargs) is None
    assert "2 to ask" in lines[0] and not client.calls

    runs = ev.answer_all(items, cache=cache, yes=True, **kwargs)
    assert runs and [r["tool"] for r in runs] == ["get_product", None]
    sent = client.calls[0]
    assert sent["tools"] == defs and sent["system"] == "s"
    assert sent["messages"] == [{"role": "user", "content": "request 1"}]

    again = ev.answer_all(items, cache=ev.RunCache(tmp_path / "runs.jsonl"), yes=True, **kwargs)
    assert again == runs and "2 cached, 0 to ask" in lines[-1]
