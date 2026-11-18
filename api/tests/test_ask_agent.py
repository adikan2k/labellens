"""The ask agent's loop with a scripted model and stub tools: steps, budget, citations,
refusals, cost, failures and tracing."""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx
import psycopg
import pytest

from api.app.ask.agent import (
    BUDGET_USED,
    MAX_TOOL_CALLS,
    Agent,
    AgentError,
    Answer,
    AskTimeout,
    Step,
    finalize,
)
from api.app.ask.prompts import PROMPT_VERSION
from api.app.ask.tools import Citations, ToolResult
from api.app.ask.tracing import Tracer
from api.tests.scripted_client import ScriptedClient, Usage, text, tool_calls

MODEL, EMBED = "claude-haiku-5-5", "voyage-4-lite"


class StubTools:
    """Answers every call with one cited product row; records what it was asked."""

    def __init__(self, fail: Exception | None = None, embedding_tokens: int = 0):
        self.citations = Citations()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail
        self.embedding_tokens = embedding_tokens

    def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append((name, arguments))
        if self.fail:
            raise self.fail
        n = len(self.calls)
        cite = self.citations.add("row", f"00{n}", f"Product {n}", f"/products/00{n}")
        content = json.dumps({"rows": [{"code": f"00{n}", "cite": cite}]})
        return ToolResult(name, arguments.get("summary", "Looked it up"), content,  # type: ignore[arg-type]
                          1, 12, embedding_tokens=self.embedding_tokens)  # fmt: skip


def _agent(client: ScriptedClient, tracer: Tracer | None = None, **kw: Any) -> Agent:
    return Agent(client, MODEL, EMBED, tracer or Tracer(), **kw)


def _events(agent: Agent, tools: Any, question: str = "cereals under 5 g sugar", **kw: Any):
    run = agent.run(question, tools, **kw)
    return run, list(run.events())


SQL = ("query_sql", {"summary": "Cereals under 5 g sugar", "sql": "select 1"})


def test_a_tool_call_streams_a_step_then_a_cited_answer() -> None:
    client = ScriptedClient(
        tool_calls(SQL),
        text("Cheerios has 3.6 g [R1]. Also [R7] made up. Fine [R1, E9]."),
    )
    tools = StubTools()
    run, events = _events(_agent(client), tools)

    step, answer = events
    assert step == Step(1, "query_sql", "Cereals under 5 g sugar", 1, 12)
    assert isinstance(answer, Answer) and not answer.refused
    assert answer.text == "Cheerios has 3.6 g [1]. Also made up. Fine [1]."
    assert answer.citations == [
        {"n": 1, "kind": "row", "ref": "001", "label": "Product 1", "url": "/products/001"}
    ]
    first, second = client.calls
    assert first["model"] == MODEL and first["thinking"] == {"type": "disabled"}
    assert first["tool_choice"] == {"type": "auto"}
    assert [t["name"] for t in first["tools"]] == ["query_sql", "query_graph", "search_explainers"]
    assert "query_graph for relationships" in first["system"][0]["text"]
    # The tool result goes back under the call's id, after the assistant's tool_use turn.
    assert second["messages"][1]["content"][0]["type"] == "tool_use"
    result = second["messages"][2]["content"][0]
    assert result["tool_use_id"] == "toolu_0_query_sql" and result["is_error"] is False
    assert run.tool_calls == 1 and run.steps == [step]


def test_after_six_calls_the_model_must_answer() -> None:
    script = [tool_calls(SQL) for _ in range(MAX_TOOL_CALLS)] + [text("Done [R6].")]
    client = ScriptedClient(*script)
    _run, events = _events(_agent(client), StubTools())
    assert [e.index for e in events if isinstance(e, Step)] == [1, 2, 3, 4, 5, 6]
    assert [c["tool_choice"]["type"] for c in client.calls] == ["auto"] * 6 + ["none"]
    assert events[-1].text == "Done [1]."  # type: ignore[union-attr]


def test_parallel_calls_past_the_budget_are_refused_not_run() -> None:
    script = [tool_calls(SQL) for _ in range(5)]
    script += [tool_calls(SQL, SQL, SQL), text("Enough.")]
    client = ScriptedClient(*script)
    tools = StubTools()
    run, _ = _events(_agent(client), tools)
    assert len(tools.calls) == 6 and run.tool_calls == 6
    results = client.calls[-1]["messages"][-1]["content"]
    assert [r["is_error"] for r in results] == [False, True, True]
    assert results[1]["content"] == BUDGET_USED


def test_refusal_marker_sets_refused_and_is_removed() -> None:
    client = ScriptedClient(text("[refused] LabelLens can't give medical advice."))
    _run, events = _events(_agent(client), StubTools(), "is this safe for my diabetes?")
    (answer,) = events
    assert answer.refused and answer.text == "LabelLens can't give medical advice."  # type: ignore[union-attr]
    assert answer.citations == []  # type: ignore[union-attr]


def test_a_model_refusal_stop_reason_is_a_refused_answer() -> None:
    client = ScriptedClient(text("", stop_reason="refusal"))
    _, events = _events(_agent(client), StubTools())
    assert events[-1].refused  # type: ignore[union-attr]


def test_cost_counts_model_and_embedding_tokens() -> None:
    client = ScriptedClient(
        tool_calls(SQL, usage=Usage(input_tokens=2000, output_tokens=100)),
        text("Done.", usage=Usage(input_tokens=3000, output_tokens=200)),
    )  # fmt: skip
    run, _ = _events(_agent(client), StubTools(embedding_tokens=10_000))
    assert run.usage.input_tokens == 5000 and run.usage.output_tokens == 300
    assert run.usage.embedding_tokens == 10_000 and run.usage.model_calls == 2
    assert run.usage.cache_read_input_tokens == run.usage.cache_creation_input_tokens == 0
    expected = (5000 * 0.10 + 300 * 0.50 + 10_000 * 0.02) / 1e6
    assert run.cost == pytest.approx(expected)


def test_cache_reads_and_writes_cost_their_multiples_of_the_input_price() -> None:
    """Haiku 5.5: input $0.10/MTok, a cache write 1.25 times it, a cache read 0.1 times it.
    The API reports input_tokens as the uncached part only."""
    client = ScriptedClient(
        tool_calls(SQL, usage=Usage(input_tokens=50, output_tokens=100,
                                    cache_creation_input_tokens=2200)),
        text("Done.", usage=Usage(input_tokens=400, output_tokens=200,
                                  cache_read_input_tokens=2200)),
    )  # fmt: skip
    run, _ = _events(_agent(client), StubTools())
    usage = run.usage
    assert usage.input_tokens == 50 + 2200 + 400 + 2200  # every input token, as before
    assert usage.cache_creation_input_tokens == 2200 and usage.cache_read_input_tokens == 2200
    assert usage.uncached_input_tokens == 450
    expected_in = (450 + 2200 * 1.25 + 2200 * 0.10) * 0.10 / 1e6
    assert run.cost == pytest.approx(expected_in + 300 * 0.50 / 1e6)
    # The same tokens all at the full input price cost more than the cached run.
    assert run.cost < (usage.input_tokens * 0.10 + 300 * 0.50) / 1e6


def test_the_tools_and_system_prompt_are_cached_with_one_marker() -> None:
    """Tools render before the system prompt, so one ephemeral marker on the system block
    caches both. The prefix must be byte-identical on every call of the run, including the
    forced-answer call where tool_choice is none; nothing after it carries a marker."""
    calls = [tool_calls(SQL) for _ in range(MAX_TOOL_CALLS)]
    client = ScriptedClient(*calls, text("Done."))
    _events(_agent(client), StubTools())
    first, last = client.calls[0], client.calls[-1]
    (block,) = first["system"]
    assert block["type"] == "text" and block["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in t for t in first["tools"])
    assert "cache_control" not in first  # no automatic marker on the varying tail
    assert last["tool_choice"] == {"type": "none"}
    for call in client.calls:
        assert call["system"] == first["system"] and call["tools"] == first["tools"]
        assert "cache_control" not in json.dumps(call["messages"])


def test_caching_can_be_turned_off_to_measure_it() -> None:
    client = ScriptedClient(text("Hi."))
    _events(_agent(client, cache_prompt=False), StubTools())
    (call,) = client.calls
    assert isinstance(call["system"], str) and "cache_control" not in json.dumps(call)


def test_a_lost_database_ends_the_run_with_tool_failed() -> None:
    client = ScriptedClient(tool_calls(SQL))
    tools = StubTools(fail=psycopg.OperationalError("server closed the connection"))
    with pytest.raises(AgentError) as caught:
        _events(_agent(client), tools)
    assert caught.value.code == "tool_failed"


def test_a_failed_model_call_is_internal() -> None:
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))  # type: ignore[arg-type]
    with pytest.raises(AgentError) as caught:
        _events(_agent(ScriptedClient(error=error)), StubTools())
    assert caught.value.code == "internal"


def test_the_deadline_stops_the_run() -> None:
    client = ScriptedClient(tool_calls(SQL), text("late"))
    with pytest.raises(AskTimeout):
        _events(_agent(client), StubTools(), timeout=-1)


def test_the_baseline_sees_only_its_tool() -> None:
    client = ScriptedClient(text("No data."))
    _events(_agent(client, tool_names=("search_explainers",)), StubTools())
    (call,) = client.calls
    assert [t["name"] for t in call["tools"]] == ["search_explainers"]
    assert "query_sql" not in call["system"][0]["text"]


def test_finalize_handles_groups_and_unknown_ids() -> None:
    cites = Citations()
    cites.add("row", "1", "A", "/products/1")
    cites.add("node", "Product:2", "B", "/graph?code=2")
    answer = finalize("A [R1, N1] and B [N1]; nothing [R5].", cites)
    assert answer.text == "A [1][2] and B [2]; nothing."
    assert [c["n"] for c in answer.citations] == [1, 2]


# --- Tracing -------------------------------------------------------------------------------


class Recorded:
    def __init__(self, log: list[tuple[str, ...]], name: str, as_type: str, fields: dict):
        self.log, self.name = log, name
        log.append(("start", name, as_type))
        self.fields = fields
        self.children: list[Recorded] = []

    def start_observation(self, *, name: str, as_type: str = "span", **fields: Any) -> Recorded:
        child = Recorded(self.log, name, as_type, fields)
        self.children.append(child)
        return child

    def update(self, **fields: Any) -> None:
        self.fields |= fields

    def end(self) -> None:
        self.log.append(("end", self.name))


class RecordingLangfuse:
    def __init__(self) -> None:
        self.log: list[tuple[str, ...]] = []
        self.root: Recorded | None = None
        self.flushed = 0
        self.trace_contexts: list[dict[str, str]] = []

    def create_trace_id(self) -> str:
        return f"{len(self.trace_contexts) + 1:032x}"

    def start_observation(
        self, *, name: str, as_type: str = "span", trace_context: Any = None, **fields: Any
    ) -> Recorded:
        self.trace_contexts.append(trace_context)
        self.root = Recorded(self.log, name, as_type, fields)
        return self.root

    def flush(self) -> None:
        self.flushed += 1


def test_a_run_is_traced_as_generations_and_tool_spans() -> None:
    langfuse = RecordingLangfuse()
    client = ScriptedClient(tool_calls(SQL), text("Done [R1]."))
    _events(_agent(client, Tracer(langfuse)), StubTools())
    starts = [entry[1:] for entry in langfuse.log if entry[0] == "start"]
    assert starts == [("ask", "agent"), ("model call", "generation"), ("query_sql", "tool"),
                      ("model call", "generation")]  # fmt: skip
    assert langfuse.log[-1] == ("end", "ask")
    root = langfuse.root
    assert root and root.fields["metadata"]["prompt_version"] == PROMPT_VERSION
    assert root.fields["output"]["text"] == "Done [1]."
    assert root.fields["metadata"]["tool_calls"] == 1


def test_a_generation_reports_cached_tokens_at_their_own_price() -> None:
    langfuse = RecordingLangfuse()
    client = ScriptedClient(
        text("Hi.", usage=Usage(input_tokens=100, output_tokens=10,
                                cache_read_input_tokens=2000, cache_creation_input_tokens=300)),
    )  # fmt: skip
    _events(_agent(client, Tracer(langfuse)), StubTools())
    assert langfuse.root is not None
    (generation,) = langfuse.root.children
    assert generation.fields["usage_details"] == {
        "input": 100, "input_cache_read": 2000, "input_cache_creation": 300, "output": 10,
    }  # fmt: skip
    cost = generation.fields["cost_details"]
    assert cost["input"] == pytest.approx(100 * 0.10 / 1e6)
    assert cost["input_cache_read"] == pytest.approx(2000 * 0.10 * 0.10 / 1e6)
    assert cost["input_cache_creation"] == pytest.approx(300 * 0.10 * 1.25 / 1e6)
    assert cost["output"] == pytest.approx(10 * 0.50 / 1e6)
    assert cost["total"] == pytest.approx(sum(v for k, v in cost.items() if k != "total"))


def test_a_broken_tracer_does_not_break_the_run() -> None:
    class Broken:
        def start_observation(self, **_: Any) -> Any:
            raise RuntimeError("langfuse down")

        def flush(self) -> None:
            raise RuntimeError("langfuse down")

    tracer = Tracer(Broken())
    client = ScriptedClient(tool_calls(SQL), text("Done."))
    _, events = _events(_agent(client, tracer), StubTools())
    assert events[-1].text == "Done."  # type: ignore[union-attr]
    tracer.flush()  # logged, not raised


def test_each_run_is_a_trace_of_its_own() -> None:
    """Never a child of the request's context: on Cloud Run that is Google's traceparent,
    sampled for only a few requests, and the other runs were silently not recorded."""
    langfuse = RecordingLangfuse()
    for _ in range(2):
        _events(_agent(ScriptedClient(text("Hi.")), Tracer(langfuse)), StubTools())
    assert langfuse.trace_contexts == [{"trace_id": f"{1:032x}"}, {"trace_id": f"{2:032x}"}]


def test_only_our_own_spans_are_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Anthropic SDK's own spans would count every model call's cost twice."""
    import langfuse

    made: dict[str, Any] = {}
    monkeypatch.setattr(langfuse, "Langfuse", lambda **kw: made.update(kw) or object())
    assert Tracer.from_keys("pk", "sk", "https://us.cloud.langfuse.com").enabled
    assert made["should_export_span"] is langfuse.is_langfuse_span
    assert made["base_url"] == "https://us.cloud.langfuse.com"


def test_tracing_is_off_without_keys() -> None:
    assert not Tracer.from_keys(None, None, None).enabled
