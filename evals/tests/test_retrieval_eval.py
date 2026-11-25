"""The retrieval eval: search methods, metrics, the query cache, the report, and the dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from api.app.ask.tools import EXPLAINER_TOP
from evals.datasets import build_retrieval as build
from evals.runners import retrieval_eval as ev

# --- Search methods ----------------------------------------------------------------------


def test_the_eval_scores_the_same_number_of_results_the_agent_sees() -> None:
    assert ev.TOP == EXPLAINER_TOP


def test_keyword_search_ranks_the_document_with_the_rare_word_first() -> None:
    docs = ["Sugar: sweet", "Carrageenan: from red seaweed", "Salt: salty and sweet"]
    bm25 = ev.BM25(docs)
    assert bm25.rank("what is carrageenan", 3)[0] == 1
    assert bm25.rank("sweet", 3)[:2] == [0, 2]  # the shorter document first
    # Nothing matches: every score is 0 and the order is the collection's.
    assert bm25.rank("blockchain", 3) == [0, 1, 2]


def test_vector_search_orders_by_cosine_like_pgvector() -> None:
    index = ev.VectorIndex(["a", "b", "c"], [[1, 0, 0], [0, 1, 0], [1, 1, 0]])
    ranked = index.search([1, 0.1, 0], 3)
    assert [doc_id for doc_id, _ in ranked] == ["a", "c", "b"]
    assert ranked[0][1] == pytest.approx(0.995, abs=1e-3)
    # Same direction, different length: cosine sees no difference; ties keep collection order.
    tie = ev.VectorIndex(["x", "y"], [[2, 0, 0], [1, 0, 0]])
    assert [doc_id for doc_id, _ in tie.search([1, 0, 0], 2)] == ["x", "y"]


def test_fusion_rewards_documents_both_methods_rank_well() -> None:
    fused = ev.rrf([["a", "c", "d"], ["b", "c", "e"]])
    assert fused[0] == "c"  # second in both beats first in one
    assert set(fused) == {"a", "b", "c", "d", "e"}


def test_metrics() -> None:
    ranked = ["x", "a", "y", "b", "z", "c"]
    assert ev.hit_at(ranked, ["a"], 1) is False
    assert ev.hit_at(ranked, ["a"], 5) is True
    assert ev.hit_at(ranked, ["c"], 5) is False
    assert ev.reciprocal_rank(ranked, ["a", "b"]) == 0.5
    assert ev.reciprocal_rank(ranked, ["nope"]) == 0.0
    assert ev.reciprocal_rank(ranked, ["c"], depth=5) == 0.0
    assert ev.precision_at(ranked, ["a", "b", "c"], 5) == 0.4


# --- Query vectors: estimate first, send only with --yes, cache --------------------------


@dataclass
class Embedded:
    vectors: list[list[float]]
    tokens: int


class FakeVoyage:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, batch: list[str]) -> Embedded:
        self.calls.append(list(batch))
        return Embedded([[float(len(q)), 1.0, 0.0] for q in batch], 3 * len(batch))


def test_nothing_is_sent_without_yes_and_the_cache_makes_reruns_free(tmp_path: Path) -> None:
    cache = tmp_path / "q.parquet"
    voyage = FakeVoyage()
    log: list[str] = []
    kwargs: dict[str, Any] = {
        "model": "m", "dim": 3, "embed": voyage, "price_per_mtok": 0.02, "cache": cache,
        "log": log.append,
    }  # fmt: skip
    assert ev.query_vectors(["what is salt", "e330"], limit=10, yes=False, **kwargs) is None
    assert voyage.calls == []
    assert "to embed with m" in log[0] and "Nothing sent" in log[-1]

    vectors = ev.query_vectors(["what is salt", "e330", "e330"], limit=10, yes=True, **kwargs)
    assert vectors is not None and set(vectors) == {"what is salt", "e330"}
    assert voyage.calls == [["what is salt", "e330"]]  # each query once

    again = ev.query_vectors(["what is salt", "e330"], limit=10, yes=False, **kwargs)
    assert again == vectors and len(voyage.calls) == 1
    # Another model is another cache entry.
    assert ev.query_vectors(["e330"], limit=10, yes=False, **{**kwargs, "model": "m2"}) is None


def test_the_limit_caps_what_is_sent(tmp_path: Path) -> None:
    voyage = FakeVoyage()
    out = ev.query_vectors(
        ["a b c", "d e f", "g h i"], model="m", dim=3, embed=voyage, price_per_mtok=0.02,
        limit=2, yes=True, cache=tmp_path / "q.parquet", log=lambda _: None,
    )  # fmt: skip
    assert out is None  # one query still has no vector
    assert sum(len(c) for c in voyage.calls) == 2


# --- The eval end to end on a tiny collection ----------------------------------------------

EXPLAINERS = [
    {"kind": "additive", "id": "en:e407", "name": "Carrageenan", "text": "red seaweed gel",
     "model": "m", "embedding": [1.0, 0.0, 0.0]},
    {"kind": "additive", "id": "en:e500ii", "name": "Sodium hydrogen carbonate",
     "text": "baking soda that raises cakes", "model": "m", "embedding": [0.0, 1.0, 0.0]},
    {"kind": "ingredient", "id": "en:salt", "name": "Salt", "text": "sodium chloride",
     "model": "m", "embedding": [0.0, 0.0, 1.0]},
]  # fmt: skip
DATASET = [
    {"id": "name-01", "kind": "name", "query": "carrageenan", "relevant": ["en:e407"],
     "written_by": "data"},
    {"id": "descriptive-01", "kind": "descriptive", "query": "what makes cakes rise",
     "relevant": ["en:e500ii"], "written_by": "Claude Code"},
    {"id": "e_number-01", "kind": "e_number", "query": "E500ii", "relevant": ["en:e500ii"],
     "written_by": "data"},
    {"id": "class-01", "kind": "class", "query": "a gelling seaweed", "cls": "en:thickener",
     "relevant": ["en:e407"], "written_by": "Claude Code (phrasing); data (answers)"},
    {"id": "no_answer-01", "kind": "no_answer", "query": "who wrote hamlet", "relevant": [],
     "written_by": "Claude Code"},
]  # fmt: skip
VECTORS = {
    "carrageenan": [1.0, 0.1, 0.0],
    "what makes cakes rise": [0.1, 1.0, 0.0],
    "E500ii": [0.0, 0.2, 1.0],  # the vector search misses this one: salt comes first
    "a gelling seaweed": [1.0, 0.0, 0.1],
    "who wrote hamlet": [0.3, 0.3, 0.3],
}


def test_run_summary_and_report() -> None:
    rows = ev.run(DATASET, EXPLAINERS, VECTORS)
    by_id = {r["id"]: r for r in rows}
    assert by_id["name-01"]["ranked"]["vector"][0] == "en:e407"
    assert by_id["e_number-01"]["ranked"]["vector"][0] == "en:salt"
    # The agent looks the E-number up exactly before the vector results.
    assert by_id["e_number-01"]["ranked"]["agent"][0] == "en:e500ii"
    assert by_id["name-01"]["ranked"]["agent"] == by_id["name-01"]["ranked"]["vector"]
    assert by_id["name-01"]["ranked"]["keyword"][0] == "en:e407"

    summary = ev.summarize(rows, collection=len(EXPLAINERS))
    vector = summary["overall"]["vector"]
    assert (vector["n"], vector["hit1"], vector["hit5"]) == (3, 2, 3)  # 3 results: all in top 5
    assert summary["by_kind"]["e_number"]["vector"]["hit1"] == 0
    assert summary["by_kind"]["e_number"]["agent"]["hit1"] == 1
    assert summary["overall"]["agent"]["hit1"] == 3
    assert summary["class"]["queries"][0]["vector"] == pytest.approx(1 / 3, abs=1e-3)
    assert summary["class"]["base_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert summary["no_answer"]["n"] == 1

    names = {e["id"]: e["name"] for e in EXPLAINERS}
    report = ev.render(summary, rows, names, model="m", collection=3, measured="2026-11-25")
    assert "# Explainer search: retrieval eval" in report
    assert "| Right explainer in the top 5 | 100% (44–100%)" in report
    assert "## Every miss by the agent's search (0)" in report
    assert "Claude Code: 2 queries" in report and "data: 2 queries" in report


# --- Building the dataset ------------------------------------------------------------------


def test_parents_and_children_answer_for_each_other_but_siblings_do_not() -> None:
    ids = ["en:e160", "en:e160a", "en:e160aii", "en:e160b", "en:e322", "en:e322i",
           "en:e339i", "en:e339ii", "en:salt"]  # fmt: skip
    g = build.groups(ids)
    assert g["en:e160b"] == ["en:e160", "en:e160b"]
    assert g["en:e160aii"] == ["en:e160", "en:e160a", "en:e160aii"]
    assert g["en:e160"] == ["en:e160", "en:e160a", "en:e160aii", "en:e160b"]
    assert g["en:e322i"] == ["en:e322", "en:e322i"]
    assert g["en:e339i"] == ["en:e339i"]  # E339ii is a sibling, not a child
    assert g["en:salt"] == ["en:salt"]
    assert build.e_number("en:e160aii") == "E160aii" and build.e_number("en:salt") is None


def test_misspellings_always_change_the_name_the_same_way() -> None:
    assert build.misspell("Carrageenan") == build.misspell("carrageenan") != "carrageenan"
    assert build.misspell("aa") == "aaa"  # nothing to swap: a letter is doubled
    assert build.spread(list(range(10)), 5) == [0, 2, 4, 6, 8]


def test_build_makes_every_kind_and_checks_written_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    explainers = [{"kind": e["kind"], "id": e["id"], "name": e["name"]} for e in EXPLAINERS]
    taxonomy = {"en:e407": {"additives_classes": {"en": "en:thickener, en:gelling-agent"}}}
    monkeypatch.setattr(build, "PER_KIND", {"name": 1, "e_number": 1, "misspelling": 1})
    monkeypatch.setattr(build, "CLASS_QUERIES", {"en:thickener": "what thickens"})
    monkeypatch.setattr(build, "DESCRIPTIVE", [("baking soda", ["en:e500ii", "en:absent"])])
    monkeypatch.setattr(build, "NO_ANSWER", ["who wrote hamlet"])
    rows = build.build(explainers, taxonomy, {"en:e407": 10, "en:e500ii": 5, "en:salt": 99})
    kinds = [r["kind"] for r in rows]
    assert set(kinds) == {"name", "e_number", "misspelling", "descriptive", "no_answer"}
    assert kinds.count("class") == 0  # a class needs at least 5 members to be asked about
    descriptive = next(r for r in rows if r["kind"] == "descriptive")
    assert descriptive["relevant"] == ["en:e500ii"]  # the absent id is dropped
    assert descriptive["written_by"] == "Claude Code"

    monkeypatch.setattr(build, "DESCRIPTIVE", [("nothing here", ["en:absent"])])
    with pytest.raises(ValueError, match="No explainer"):
        build.build(explainers, taxonomy, {})


# --- The committed dataset and cache -------------------------------------------------------


def test_the_committed_dataset_points_at_explainers_that_exist() -> None:
    dataset = ev.load_dataset()
    ids = {e["id"] for e in ev.load_explainers()}
    assert len({r["id"] for r in dataset}) == len(dataset)
    for row in dataset:
        assert set(row["relevant"]) <= ids, row["id"]
        assert bool(row["relevant"]) == (row["kind"] != "no_answer"), row["id"]


def test_every_query_has_a_cached_vector_so_reruns_cost_nothing() -> None:
    cache = ev.load_cache()
    model = {e["model"] for e in ev.load_explainers()}.pop()
    missing = [
        r["query"] for r in ev.load_dataset()
        if ev.query_key(model, 1024, r["query"]) not in cache
    ]  # fmt: skip
    assert missing == []


def test_the_report_and_its_numbers_are_committed() -> None:
    data = json.loads((ev.RESULTS / "retrieval.json").read_text("utf-8"))
    assert len(data["queries"]) == len(ev.load_dataset())
    assert data["summary"]["overall"]["vector"]["n"] > 0
