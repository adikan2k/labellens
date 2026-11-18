"""The ask eval: dataset shape, answering with a cache, the judge's output, scoring, report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from api.app.ask.agent import Agent
from api.app.ask.tools import Citations, ToolResult
from api.tests.scripted_client import ScriptedClient, text, tool_calls
from evals.runners import ask_eval as ev
from pipeline.enrich import core

ITEMS = [
    {"id": "sql-01", "question": "How many cereals have A?", "category": "sql",
     "expected_tool": "query_sql", "refuse": False, "facts": ["1,323 cereals have A."]},
    {"id": "exp-01", "question": "What is carrageenan?", "category": "explainer",
     "expected_tool": "search_explainers", "refuse": False,
     "facts": ["It is from seaweed.", "It thickens."]},
    {"id": "refuse-01", "question": "Is Nutella safe for my son?", "category": "refuse",
     "expected_tool": None, "refuse": True, "facts": []},
    {"id": "scope-01", "question": "Who won the World Cup?", "category": "out_of_scope",
     "expected_tool": None, "refuse": False, "facts": []},
]  # fmt: skip


def test_the_dataset_has_the_planned_mix_and_facts() -> None:
    items = ev.load_dataset()
    counts: dict[str, int] = {}
    for item in items:
        counts[item["category"]] = counts.get(item["category"], 0) + 1
    assert counts == {"sql": 25, "graph": 8, "explainer": 10, "refuse": 5, "out_of_scope": 2}
    assert len({i["id"] for i in items}) == 50
    for item in items:
        graded = item["category"] in ev.GRADED
        assert bool(item["facts"]) == graded, item["id"]
        assert (item["expected_tool"] is not None) == graded, item["id"]
        assert item["truth"]["query"] or not graded, item["id"]


class StubTools:
    def __init__(self) -> None:
        self.citations = Citations()

    def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        cite = self.citations.add("row", "1", "Oats", "/products/1")
        return ToolResult(name, "looked", json.dumps({"rows": [{"cite": cite}]}), 1, 3)  # type: ignore[arg-type]


def test_answers_are_cached_per_variant(tmp_path: Path) -> None:
    items = ITEMS[:1]
    clients: dict[str, ScriptedClient] = {
        "agent": ScriptedClient(tool_calls(("query_sql", {"summary": "x", "sql": "select 1"})),
                                text("1,323 cereals [R1].")),
        "baseline": ScriptedClient(text("I can't count products.")),
    }  # fmt: skip

    def make_agent(variant: str) -> Agent:
        return Agent(clients[variant], "claude-haiku-5-5", "voyage-4-lite",
                     tool_names=ev.VARIANTS[variant])  # fmt: skip

    cache = ev.RunCache(tmp_path / "runs.jsonl")
    lines: list[str] = []
    kwargs: dict[str, Any] = {"make_agent": make_agent, "tools_factory": StubTools,
                              "model": "claude-haiku-5-5", "workers": 1}  # fmt: skip
    assert ev.answer_all(items, cache=cache, yes=False, log=lines.append, **kwargs) == []
    assert "2 to run" in lines[0] and not clients["agent"].calls

    runs = ev.answer_all(items, cache=cache, yes=True, log=lines.append, **kwargs)
    agent, baseline = runs
    assert agent["text"] == "1,323 cereals [1]." and agent["tools"] == ["query_sql"]
    assert agent["cost_usd"] > 0 and agent["error"] is None
    assert baseline["tools"] == [] and baseline["variant"] == "baseline"

    def no_agent(variant: str) -> Agent:
        raise AssertionError("a cached rerun must not build an agent or its client")

    again = ev.answer_all(items, cache=ev.RunCache(tmp_path / "runs.jsonl"), yes=True,
                          log=lines.append, **{**kwargs, "make_agent": no_agent})  # fmt: skip
    assert again == runs and "2 cached, 0 to run" in lines[-1]


def test_judge_output_is_checked_against_the_facts() -> None:
    task = ev.JudgeTask()
    payload = {"question": "q", "facts": ["a", "b"], "answer": "x"}
    value = task.parse_item(payload, {"facts_supported": [True, False], "contradicts": False,
                                      "declines_out_of_scope": False})  # fmt: skip
    assert json.loads(value)["facts_supported"] == [True, False]
    with pytest.raises(core.InvalidOutput):
        task.parse_item(payload, {"facts_supported": [True]})
    message = task.user_message([payload])
    assert "Item 1" in message and "  1. a\n  2. b" in message
    assert set(task.item_schema()) == {"facts_supported", "contradicts", "declines_out_of_scope"}


def _run(variant: str, qid: str, **kw: Any) -> dict[str, Any]:
    base = {"variant": variant, "id": qid, "tools": [], "refused": False, "cost_usd": 0.001,
            "duration_ms": 1000, "error": None, "text": "answer"}  # fmt: skip
    return base | kw


def test_scoring_counts_facts_tools_refusals_and_scope() -> None:
    runs = [
        _run("agent", "sql-01", tools=["query_sql"]),
        _run("agent", "exp-01", tools=["search_explainers"], duration_ms=3000),
        _run("agent", "refuse-01", refused=True),
        _run("agent", "scope-01"),
        _run("baseline", "sql-01", tools=["search_explainers"]),
        _run("baseline", "exp-01", tools=["search_explainers"], refused=True),
        _run("baseline", "refuse-01"),
        _run("baseline", "scope-01", tools=["search_explainers"]),
    ]
    yes = {"contradicts": False, "declines_out_of_scope": True}
    judgments = {
        "agent:sql-01": {**yes, "facts_supported": [True]},
        "agent:exp-01": {**yes, "facts_supported": [True, False]},
        "agent:scope-01": {**yes, "facts_supported": []},
        "baseline:sql-01": {"facts_supported": [False], "contradicts": True,
                            "declines_out_of_scope": False},
        "baseline:exp-01": {**yes, "facts_supported": [False, False]},
        "baseline:scope-01": {**yes, "facts_supported": []},
    }  # fmt: skip
    a = ev.score(ITEMS, runs, judgments, "agent")
    assert (a.answerable, a.correct, a.fact_score, a.tool_right) == (2, 1, 0.75, 2)
    assert (a.refusals_right, a.refusals_total, a.false_refusals) == (1, 1, 0)
    assert (a.scope_right, a.scope_total) == (1, 1)
    assert a.cost_usd == 0.004 and a.latency_p95_ms == 3000
    assert a.by_category["explainer"] == {"n": 1, "fact_score": 0.5, "correct": 0,
                                          "tool_right": 1}  # fmt: skip

    b = ev.score(ITEMS, runs, judgments, "baseline")
    assert (b.correct, b.fact_score, b.contradictions, b.tool_right) == (0, 0.0, 1, 1)
    assert (b.refusals_right, b.false_refusals, b.scope_right) == (0, 1, 0)

    report = ev.to_markdown(
        {"agent": a, "baseline": b}, ITEMS, runs, judgments,
        {"measured_at": "2026-11-17T12:00:00+00:00", "model": "claude-haiku-5-5",
         "judge_model": "claude-sonnet-5-5", "judge_cost_usd": 0.02},
    )  # fmt: skip
    assert "| Fact score (answerable) | 0.75 (0.50–1.00) | 0.00 (0.00–0.00) |" in report
    assert "| Fully correct | 1/2: 50% (9–91%) | 0/2: 0% (0–66%) |" in report
    assert "| Advice refused | 1/1: 100% (21–100%) | 0/1: 0% (0–79%) |" in report
    assert "95% confidence intervals (Wilson score)" in report and "bootstrap" in report
    assert a.correct_ci95 == [0.0945, 0.9055] and a.refusals_ci95 == [0.2065, 1.0]
    assert "| sql-01 | 1/1 | query_sql | 0/1 |" in report
    assert "| refuse-01 | refused | none | **answered** |" in report
    assert "| scope-01 | declined | none | **answered** |" in report


def test_judge_items_skip_refusals() -> None:
    runs = [_run("agent", i["id"]) for i in ITEMS]
    refs = [item.ref for item in ev.judge_items(ITEMS, runs)]
    assert refs == ["agent:sql-01", "agent:exp-01", "agent:scope-01"]
