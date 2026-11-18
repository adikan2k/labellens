"""The explainer embedding task and the Voyage client, against a fake Voyage (no network)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from api.app.config import EMBEDDING_PRICES, embedding_price_per_mtok
from api.app.embeddings import DIMENSION, EmbeddingsUnavailable, Voyage, vector_literal
from pipeline.enrich import embeddings
from pipeline.tests.fake_voyage import FakeVoyageServer, fake_vector

TEXTS = [
    {"kind": "additive", "id": "en:e330", "name": "Citric acid", "text": "An acid from citrus."},
    {"kind": "additive", "id": "en:e322", "name": "Lecithins", "text": "An emulsifier."},
    {"kind": "ingredient", "id": "en:sugar", "name": "Sugar", "text": "A sweetener."},
]


def _run(server: FakeVoyageServer, store: Path, texts=TEXTS, **kw) -> embeddings.Summary:
    options = {"limit": 100, "yes": True, "log": lambda *_: None} | kw
    return embeddings.run(
        texts,
        voyage_factory=server.client,
        model="voyage-4-lite",
        price_per_mtok=0.02,
        store=store,
        **options,
    )


def test_without_yes_nothing_is_sent_and_the_estimate_is_printed(tmp_path: Path) -> None:
    server, lines = FakeVoyageServer(), []
    summary = _run(server, tmp_path / "e.parquet", yes=False, log=lines.append)
    assert server.requests == [] and not (tmp_path / "e.parquet").exists()
    assert summary.estimated_cost > 0
    assert any("sending 3" in line and "$" in line for line in lines)
    assert any("Add --yes" in line for line in lines)


def test_sends_documents_and_caches_them(tmp_path: Path) -> None:
    server, store = FakeVoyageServer(), tmp_path / "e.parquet"
    first = _run(server, store)
    assert first.sent == 3 and first.tokens > 0
    (request,) = server.requests
    assert request["input_type"] == "document" and request["output_dimension"] == DIMENSION
    assert request["input"][0] == "Citric acid: An acid from citrus."
    assert request["authorization"] == "Bearer test-key"

    rows = embeddings.load_store(store)
    assert len(rows) == 3
    row = next(r for r in rows.values() if r["id"] == "en:e330")
    assert row["embedding"] == pytest.approx(fake_vector("Citric acid: An acid from citrus."))

    again = _run(server, store)
    assert again.sent == 0 and again.cached == 3 and len(server.requests) == 1


def test_a_changed_text_is_resent_and_the_old_vector_dropped(tmp_path: Path) -> None:
    server, store = FakeVoyageServer(), tmp_path / "e.parquet"
    _run(server, store)
    changed = [TEXTS[0] | {"text": "An acid found in lemons."}, *TEXTS[1:]]
    summary = _run(server, store, texts=changed)
    assert summary.sent == 1 and summary.cached == 2
    rows = embeddings.load_store(store)
    assert len(rows) == 3
    assert {r["text"] for r in rows.values() if r["id"] == "en:e330"} == {
        "An acid found in lemons."
    }

    _run(server, store, texts=TEXTS[1:])  # an explainer that no longer exists
    assert {r["id"] for r in embeddings.load_store(store).values()} == {"en:e322", "en:sugar"}


def test_limit_caps_what_is_sent(tmp_path: Path) -> None:
    server, store = FakeVoyageServer(), tmp_path / "e.parquet"
    assert _run(server, store, limit=2).sent == 2
    assert _run(server, store, limit=2).sent == 1  # the rest, next run


def test_batches_are_saved_as_they_finish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embeddings, "BATCH", 2)
    server, store = FakeVoyageServer(), tmp_path / "e.parquet"
    calls = 0
    original = server.handler

    def fail_second(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            return httpx.Response(500, json={"detail": "down"})
        return original(request)

    server.handler = fail_second  # type: ignore[method-assign]
    with pytest.raises(EmbeddingsUnavailable, match="500"):
        _run(server, store)
    assert len(embeddings.load_store(store)) == 2  # the first batch survived


def test_voyage_client_checks_its_inputs_and_answers() -> None:
    with pytest.raises(EmbeddingsUnavailable, match="not set"):
        FakeVoyageServer().client(key=None).embed(["x"], "query")
    with pytest.raises(EmbeddingsUnavailable, match="403"):
        FakeVoyageServer(status=403).client().embed(["x"], "query")
    with pytest.raises(ValueError, match="at most"):
        FakeVoyageServer().client().embed(["x"] * 1001, "document")
    assert FakeVoyageServer().client().embed([], "query").vectors == []

    result = FakeVoyageServer().client().embed(["sugar", "salt"], "query")
    assert result.vectors[0] == pytest.approx(fake_vector("sugar"))  # sorted back by index
    assert result.vectors[1] == pytest.approx(fake_vector("salt"))

    def short(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": [0.1], "index": 0}]})

    bad = Voyage("k", "voyage-4-lite", client=httpx.Client(transport=httpx.MockTransport(short)))
    with pytest.raises(EmbeddingsUnavailable, match="wrong number or size"):
        bad.embed(["x"], "query")


def test_vector_literal_and_prices() -> None:
    assert vector_literal([0.5, -0.25, 1e-8]) == "[0.5,-0.25,1e-08]"
    assert embedding_price_per_mtok("voyage-4-lite") == EMBEDDING_PRICES["voyage-4-lite"]
    with pytest.raises(ValueError, match="No price"):
        embedding_price_per_mtok("voyage-unknown")


def test_main_requires_a_key_before_sending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(embeddings, "load_texts", lambda _path: TEXTS)
    monkeypatch.setattr(embeddings, "OUTPUT", tmp_path / "e.parquet")
    monkeypatch.setenv("EMBEDDINGS_API_KEY", "")
    from api.app.config import get_settings

    get_settings.cache_clear()
    try:
        assert embeddings.main(["--limit", "5"]) == 0  # estimate only, no key needed
        assert "Add --yes" in capsys.readouterr().out
    finally:
        get_settings.cache_clear()
