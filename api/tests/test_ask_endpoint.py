"""POST /ask end to end with a scripted model: the event stream, the run log, the rate limit,
the daily cap's replays, failures, and the event payloads against the contract."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import anthropic
import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app.ask.service import (
    CAP_REACHED,
    NO_REPLAY,
    Replay,
    choose_replay,
    client_address,
    client_hash,
)
from api.app.config import Settings
from api.app.db import DictConnection
from api.app.graph import Graph
from api.app.main import ASK_NOT_CONFIGURED, create_app
from api.app.schemas import AskAnswer, AskError, AskRequest, AskStep, Citation
from api.tests.scripted_client import ScriptedClient, text, tool_calls
from api.tests.test_contract_match import CONTRACT, shape
from pipeline.tests.fake_voyage import FakeVoyageServer

SQL_CALL = (
    "query_sql",
    {"summary": "Best-known products", "sql": "select code, name, brand from products "
     "order by rank_pos limit 2"},
)  # fmt: skip


def _app(serving_url: str, readonly_url: str, client: ScriptedClient, **settings: Any):
    values = {"database_url": serving_url, "database_url_readonly": readonly_url} | settings
    app = create_app(Settings(_env_file=None, **values))  # pyright: ignore[reportCallIssue]
    app.state.graph = Graph(driver=None)
    app.state.ask_client = client
    app.state.voyage = FakeVoyageServer().client()
    return app


@pytest.fixture
def ip(request: pytest.FixtureRequest) -> str:
    """A client address of its own per test, so rate limits never cross tests."""
    return f"203.0.113.{abs(hash(request.node.name)) % 250 + 1}"


def _events(response: Any) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in response.text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def _ask(client: TestClient, question: str, ip: str) -> Any:
    # The first entry is client-supplied and ignored; the last is the real address.
    headers = {"X-Forwarded-For": f"198.51.100.7, {ip}"}
    return client.post("/ask", json={"question": question}, headers=headers)


def _runs(serving_url: str, ip: str, hash_key: bytes) -> list[dict[str, Any]]:
    with DictConnection.connect(serving_url, row_factory=dict_row) as pg:
        return pg.execute(
            "select * from app.ask_runs where client_hash = %s order by id",
            [client_hash(hash_key, ip)],
        ).fetchall()


@pytest.fixture
def cleanup(serving_url: str) -> Iterator[None]:
    yield
    with psycopg.connect(serving_url, autocommit=True) as pg:
        pg.execute("delete from app.ask_runs where client_hash <> 'test'")


def test_steps_stream_then_a_cited_answer(
    serving_url: str, readonly_url: str, ip: str, cleanup: None
) -> None:
    scripted = ScriptedClient(tool_calls(SQL_CALL), text("The best known is [R1], then [R2]."))
    app = _app(serving_url, readonly_url, scripted)
    with TestClient(app) as client:
        response = _ask(client, "  What are the best-known products?  ", ip)
        key = app.state.ask.hash_key
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert [name for name, _ in events] == ["step", "answer"]
    step = AskStep.model_validate(events[0][1])
    assert step.index == 1 and step.tool == "query_sql" and step.row_count == 2
    answer = AskAnswer.model_validate(events[1][1])
    assert answer.text == "The best known is [1], then [2]."
    assert [c.url for c in answer.citations] == [
        f"/products/{c.ref}" for c in answer.citations
    ] and len(answer.citations) == 2
    assert not answer.refused and not answer.replay
    assert answer.source.name == "Open Food Facts"
    assert scripted.calls[0]["messages"][0]["content"] == "What are the best-known products?"

    (run,) = _runs(serving_url, ip, key)
    assert run["outcome"] == "answer" and run["tool_calls"] == 1
    assert run["input_tokens"] == 2000 and float(run["cost_usd"]) > 0
    assert run["model"] == "claude-haiku-5-5" and run["prompt_version"] == "ask-v1"
    assert ip not in json.dumps(run, default=str)  # only the keyed hash is stored


def test_the_rate_limit_answers_429_before_streaming(
    serving_url: str, readonly_url: str, ip: str, cleanup: None
) -> None:
    scripted = ScriptedClient(text("One."), text("Two."), text("Elsewhere."))
    app = _app(serving_url, readonly_url, scripted, ask_rate_limit_per_hour=2)
    with TestClient(app) as client:
        assert _ask(client, "first question", ip).status_code == 200
        assert _ask(client, "second question", ip).status_code == 200
        limited = _ask(client, "third question", ip)
        assert len(scripted.calls) == 2  # the third never reached the model
        other = _ask(client, "from another address", ip.replace("203.0.113.", "192.0.2."))
    assert limited.status_code == 429
    assert 3000 <= int(limited.headers["Retry-After"]) <= 3601
    body = limited.json()
    assert "2 questions this hour" in body["detail"] and body["source"]["name"]
    assert other.status_code == 200 and len(scripted.calls) == 3  # its own limit


def test_over_the_daily_cap_a_replay_is_served(
    serving_url: str, readonly_url: str, ip: str, cleanup: None
) -> None:
    replays = [
        Replay("What is carrageenan?", [], {"text": "A seaweed thickener [1].",
               "citations": [], "refused": False}),
        Replay("Cereals under 5 g sugar", [
            {"index": 1, "tool": "query_sql", "summary": "Cereals", "row_count": 3,
             "duration_ms": 80}
        ], {"text": "Three cereals [1].", "citations": [
            {"n": 1, "kind": "row", "ref": "1", "label": "Oats", "url": "/products/1"}
        ], "refused": False}),
    ]  # fmt: skip
    scripted = ScriptedClient()
    app = _app(serving_url, readonly_url, scripted, ask_daily_spend_cap_usd=0.0)
    app.state.ask_replays = replays
    with TestClient(app) as client:
        response = _ask(client, "which cereals have little sugar", ip)
        key = app.state.ask.hash_key
    events = _events(response)
    assert [name for name, _ in events] == ["step", "answer"]
    answer = AskAnswer.model_validate(events[-1][1])
    assert answer.replay and answer.text.startswith(CAP_REACHED)
    assert "Example question: Cereals under 5 g sugar" in answer.text
    assert scripted.calls == []
    (run,) = _runs(serving_url, ip, key)
    assert run["outcome"] == "replay" and run["replay"] and float(run["cost_usd"]) == 0


def test_over_the_cap_without_replays_says_so(
    serving_url: str, readonly_url: str, ip: str, cleanup: None
) -> None:
    app = _app(serving_url, readonly_url, ScriptedClient(), ask_daily_spend_cap_usd=0.0)
    with TestClient(app) as client:
        app.state.ask.replays = []  # as before any replay is recorded
        events = _events(_ask(client, "anything at all", ip))
    answer = AskAnswer.model_validate(events[-1][1])
    assert answer.replay and answer.text == NO_REPLAY


@pytest.mark.parametrize(
    ("settings", "script", "code"),
    [
        ({"ask_timeout_seconds": -1}, [text("late")], "timeout"),
        ({}, [], "internal"),
    ],
)
def test_failures_end_with_an_error_event(
    serving_url: str, readonly_url: str, ip: str, cleanup: None,
    settings: dict[str, Any], script: list[Any], code: str,
) -> None:  # fmt: skip
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://x"))  # type: ignore[arg-type]
    scripted = ScriptedClient(*script, error=None if script else error)
    app = _app(serving_url, readonly_url, scripted, **settings)
    with TestClient(app) as client:
        response = _ask(client, "a question", ip)
        key = app.state.ask.hash_key
    ((name, data),) = _events(response)
    assert name == "error"
    assert AskError.model_validate(data).code == code
    (run,) = _runs(serving_url, ip, key)
    assert run["outcome"] == code


def test_without_the_read_only_database_ask_is_unavailable(serving_url: str) -> None:
    settings = Settings(_env_file=None, database_url=serving_url)  # pyright: ignore[reportCallIssue]
    app = create_app(settings)
    app.state.ask_client = ScriptedClient()
    with TestClient(app) as client:
        response = client.post("/ask", json={"question": "anything"})
    assert response.status_code == 503 and response.json()["detail"] == ASK_NOT_CONFIGURED


def test_a_short_question_is_invalid(serving_url: str, readonly_url: str) -> None:
    with TestClient(_app(serving_url, readonly_url, ScriptedClient())) as client:
        response = client.post("/ask", json={"question": "hi"})
    assert response.status_code == 422 and "question" in response.json()["detail"]


# --- Pieces --------------------------------------------------------------------------------


def test_client_address_takes_the_last_forwarded_entry() -> None:
    assert client_address("1.1.1.1, 2.2.2.2", "10.0.0.1") == "2.2.2.2"
    assert client_address("3.3.3.3", None) == "3.3.3.3"
    assert client_address(None, "10.0.0.1") == "10.0.0.1"
    assert client_address(" , ", None) == "unknown"
    first, again = client_hash(b"k", "2.2.2.2"), client_hash(b"k", "2.2.2.2")
    assert first == again and first != client_hash(b"other", "2.2.2.2")
    assert "2.2.2.2" not in first and len(first) == 32


def test_choose_replay_by_shared_words() -> None:
    replays = [
        Replay("What is carrageenan?", [], {}),
        Replay("Cereals under 5 g sugar without colours", [], {}),
        Replay("Swaps for Coca-Cola", [], {}),
    ]
    assert choose_replay(replays, "low sugar cereals") is replays[1]
    assert choose_replay(replays, "carrageenan in yogurt") is replays[0]
    assert choose_replay(replays, "zzz") is replays[0]  # nothing shared: the first
    assert choose_replay([], "anything") is None


@pytest.mark.parametrize(
    ("model", "component"),
    [(AskRequest, "AskRequest"), (AskStep, "AskStep"), (Citation, "Citation"),
     (AskAnswer, "AskAnswer"), (AskError, "AskError")],
)  # fmt: skip
def test_event_payloads_match_the_contract(model: Any, component: str) -> None:
    # Responses are compared as serialized (defaults always present); the request as accepted.
    mode = "validation" if model is AskRequest else "serialization"
    generated = model.model_json_schema(ref_template="#/$defs/{model}", mode=mode)
    contract = CONTRACT["components"]["schemas"][component]
    assert shape(generated, generated) == shape(CONTRACT, contract)
    events = CONTRACT["paths"]["/ask"]["post"]["responses"]["200"]["x-sse-events"]
    assert set(events) == {"step", "answer", "error"}
