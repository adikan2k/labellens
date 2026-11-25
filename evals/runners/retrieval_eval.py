"""Retrieval eval: does the ask agent's explainer search find the right explainer?

The agent's `search_explainers` tool first looks up any E-number in the question exactly
(`e_number_ids` and `pick_exact`, imported from the tool itself), then fills the 5 results
with the explainers nearest by cosine distance in pgvector, exact search over all 1,019. This
runner does the same on the same vectors, which are committed
(pipeline/enrich/outputs/explainer_embeddings.parquet, the file the serving loader reads), so
it needs no database. Three comparisons run on the same documents ("Name: explainer", the
text that was embedded):

- vector: the vector search alone, as the tool was before the E-number lookup;
- keyword: BM25 (k1 1.2, b 0.75) over lower-cased words and numbers;
- hybrid: reciprocal rank fusion (k 60) of the vector and keyword rankings, top 50 of each.

Queries and answers: evals/datasets/retrieval.jsonl (evals/datasets/build_retrieval.py says
who wrote which). Metrics, for queries with an answer: hit@1, hit@5 (the agent sees 5) and
MRR@10. For class queries, precision@5 against the share of the collection in that class. For
off-topic queries, how similar their best match is, against the answerable ones.

Only the queries are sent to Voyage, once: vectors are cached by model and query
(evals/cache/retrieval_queries.parquet, committed), so a rerun costs nothing.

    uv run python -m evals.runners.retrieval_eval --limit 200          # estimate
    uv run python -m evals.runners.retrieval_eval --limit 200 --yes    # send, then report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import tempfile
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from api.app.ask.tools import e_number_ids, pick_exact
from evals.runners.stats import INTERVAL_NOTE, bootstrap_mean, ci95, pct_ci

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "retrieval.jsonl"
EXPLAINERS = ROOT / "pipeline" / "enrich" / "outputs" / "explainer_embeddings.parquet"
CACHE = ROOT / "evals" / "cache" / "retrieval_queries.parquet"
RESULTS = ROOT / "evals" / "results"

TOP = 5  # what search_explainers returns (api/app/ask/tools.py, EXPLAINER_TOP)
MRR_DEPTH = 10
FUSION_DEPTH = 50
RRF_K = 60
CHARS_PER_TOKEN = 3.0  # conservative; Voyage bills about 4 characters a token
METHODS = ("agent", "vector", "keyword", "hybrid")
METHOD_NAMES = {
    "agent": "The agent's search",
    "vector": "Vector alone",
    "keyword": "Keyword (BM25)",
    "hybrid": "Hybrid",
}
ANSWERABLE = ("name", "e_number", "misspelling", "descriptive")
KIND_NAMES = {
    "name": "Name",
    "e_number": "E-number",
    "misspelling": "Misspelt name",
    "descriptive": "Description, no name",
    "class": "What it does (class)",
    "no_answer": "Off-topic",
}
Log = Callable[[str], None]


# --- Data ------------------------------------------------------------------------------------


def load_dataset(path: Path = DATASET) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def load_explainers(path: Path = EXPLAINERS) -> list[dict[str, Any]]:
    import duckdb

    with duckdb.connect() as con:
        cursor = con.execute(
            "select kind, id, name, text, model, embedding from read_parquet(?) order by id",
            [str(path)],
        )
        names = [d[0] for d in cursor.description]
        return [dict(zip(names, row, strict=True)) for row in cursor.fetchall()]


def document(explainer: dict[str, Any]) -> str:
    """The text that was embedded for an explainer (pipeline/enrich/embeddings.py)."""
    return f"{explainer['name']}: {explainer['text']}"


# --- Search ----------------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class BM25:
    """Okapi BM25 over a small fixed collection, the usual keyword-search baseline."""

    def __init__(self, docs: Sequence[str], k1: float = 1.2, b: float = 0.75):
        self.k1, self.b = k1, b
        self.terms = [Counter(tokenize(d)) for d in docs]
        self.lengths = [sum(t.values()) for t in self.terms]
        self.avg = statistics.fmean(self.lengths) if self.lengths else 0.0
        df: Counter[str] = Counter()
        for t in self.terms:
            df.update(t.keys())
        n = len(docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}

    def scores(self, query: str) -> list[float]:
        words = [w for w in tokenize(query) if w in self.idf]
        out = []
        for tf, length in zip(self.terms, self.lengths, strict=True):
            norm = self.k1 * (1 - self.b + self.b * length / (self.avg or 1))
            out.append(
                sum(self.idf[w] * tf[w] * (self.k1 + 1) / (tf[w] + norm) for w in words if w in tf)
            )
        return out

    def rank(self, query: str, n: int) -> list[int]:
        """Indexes of the n best documents; ties (including all zeros) in collection order."""
        s = self.scores(query)
        return sorted(range(len(s)), key=lambda i: (-s[i], i))[:n]


class VectorIndex:
    """Exact cosine search, as pgvector's `<=>` orders it, in an in-memory DuckDB table."""

    def __init__(self, ids: Sequence[str], vectors: Sequence[Sequence[float]]):
        import duckdb

        self.dim = len(vectors[0])
        self.con = duckdb.connect()
        self.con.execute(f"create table docs (pos integer, id varchar, v float[{self.dim}])")
        self.con.executemany(
            "insert into docs values (?, ?, ?)",
            [[i, doc_id, list(v)] for i, (doc_id, v) in enumerate(zip(ids, vectors, strict=True))],
        )

    def search(self, vector: Sequence[float], n: int) -> list[tuple[str, float]]:
        rows = self.con.execute(
            f"select id, array_cosine_similarity(v, ?::float[{self.dim}]) as s "
            "from docs order by s desc, pos limit ?",
            [list(vector), n],
        ).fetchall()
        return [(doc_id, float(s)) for doc_id, s in rows]


def rrf(rankings: Sequence[Sequence[str]], k: int = RRF_K, n: int = FUSION_DEPTH) -> list[str]:
    """Reciprocal rank fusion: each list adds 1 / (k + rank); ties keep first-seen order."""
    score: dict[str, float] = defaultdict(float)
    order: dict[str, int] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, 1):
            score[doc_id] += 1 / (k + rank)
            order.setdefault(doc_id, len(order))
    return sorted(score, key=lambda d: (-score[d], order[d]))[:n]


# --- Metrics ---------------------------------------------------------------------------------


def hit_at(ranked: Sequence[str], relevant: Sequence[str], k: int) -> bool:
    return any(doc_id in relevant for doc_id in ranked[:k])


def reciprocal_rank(
    ranked: Sequence[str], relevant: Sequence[str], depth: int = MRR_DEPTH
) -> float:
    for rank, doc_id in enumerate(ranked[:depth], 1):
        if doc_id in relevant:
            return 1 / rank
    return 0.0


def precision_at(ranked: Sequence[str], relevant: Sequence[str], k: int) -> float:
    top = ranked[:k]
    return sum(doc_id in relevant for doc_id in top) / len(top) if top else 0.0


# --- Query vectors, cached -------------------------------------------------------------------


def query_key(model: str, dim: int, query: str) -> str:
    return hashlib.sha256(f"{model}|{dim}|query|{query}".encode()).hexdigest()[:32]


def load_cache(path: Path = CACHE) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    import duckdb

    with duckdb.connect() as con:
        cursor = con.execute("select * from read_parquet(?)", [str(path)])
        names = [d[0] for d in cursor.description]
        return {r[0]: dict(zip(names, r, strict=True)) for r in cursor.fetchall()}


def save_cache(rows: dict[str, dict[str, Any]], path: Path = CACHE) -> None:
    import duckdb

    dim = len(next(iter(rows.values()))["embedding"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, duckdb.connect() as con:
        con.execute(
            f"create table q (key varchar, model varchar, query varchar, embedding float[{dim}])"
        )
        con.executemany(
            "insert into q values (?, ?, ?, ?)",
            [[k, r["model"], r["query"], list(r["embedding"])] for k, r in sorted(rows.items())],
        )
        staged = Path(tmp) / "q.parquet"
        con.execute("copy q to ? (format parquet, compression zstd)", [str(staged)])
        staged.replace(path)


def query_vectors(
    queries: Sequence[str],
    *,
    model: str,
    dim: int,
    embed: Callable[[list[str]], Any],
    price_per_mtok: float,
    limit: int,
    yes: bool,
    cache: Path = CACHE,
    log: Log = print,
) -> dict[str, list[float]] | None:
    """Each query's vector, from the cache or Voyage. None when some are missing and not --yes."""
    known = load_cache(cache)
    unique = list(dict.fromkeys(queries))
    todo = [q for q in unique if query_key(model, dim, q) not in known]
    tokens = math.ceil(sum(len(q) for q in todo) / CHARS_PER_TOKEN)
    log(
        f"Queries: {len(unique) - len(todo)} cached, {len(todo)} to embed with {model} "
        f"(about {tokens:,} tokens, at most ${tokens * price_per_mtok / 1e6:.5f})."
    )
    if todo and not yes:
        log("Nothing sent. Add --yes to embed them.")
        return None
    todo = todo[: max(limit, 0)]
    for start in range(0, len(todo), 128):
        batch = todo[start : start + 128]
        embedded = embed(batch)
        for q, vector in zip(batch, embedded.vectors, strict=True):
            known[query_key(model, dim, q)] = {"model": model, "query": q, "embedding": vector}
    if todo:
        save_cache(known, cache)
    missing = [q for q in unique if query_key(model, dim, q) not in known]
    if missing:
        log(f"{len(missing)} queries still have no vector: raise --limit.")
        return None
    return {q: list(known[query_key(model, dim, q)]["embedding"]) for q in unique}


# --- The eval --------------------------------------------------------------------------------


def run(
    dataset: Sequence[dict[str, Any]],
    explainers: Sequence[dict[str, Any]],
    vectors: dict[str, list[float]],
) -> list[dict[str, Any]]:
    """Every query ranked by every method: top FUSION_DEPTH ids, and the best cosine score."""
    ids = [e["id"] for e in explainers]
    index = VectorIndex(ids, [e["embedding"] for e in explainers])
    bm25 = BM25([document(e) for e in explainers])
    rows = []
    for item in dataset:
        nearest = index.search(vectors[item["query"]], FUSION_DEPTH)
        vector = [doc_id for doc_id, _ in nearest]
        keyword = [ids[i] for i in bm25.rank(item["query"], FUSION_DEPTH)]
        exact = pick_exact(e_number_ids(item["query"]), ids)
        agent = exact + [doc_id for doc_id in vector if doc_id not in exact]
        rows.append({
            **item,
            "ranked": {
                "agent": agent,
                "vector": vector,
                "keyword": keyword,
                "hybrid": rrf([vector, keyword]),
            },
            "top_similarity": round(nearest[0][1], 4) if nearest else None,
        })  # fmt: skip
    return rows


def _mrr(values: list[float]) -> dict[str, Any]:
    low, high = bootstrap_mean(values)
    return {"mean": round(statistics.fmean(values), 4) if values else 0.0,
            "ci": [round(low, 4), round(high, 4)]}  # fmt: skip


def summarize(rows: Sequence[dict[str, Any]], collection: int) -> dict[str, Any]:
    """Metrics per method, overall (answerable kinds pooled) and per kind."""

    def scored(subset: Sequence[dict[str, Any]], method: str) -> dict[str, Any]:
        n = len(subset)
        h1 = sum(hit_at(r["ranked"][method], r["relevant"], 1) for r in subset)
        h5 = sum(hit_at(r["ranked"][method], r["relevant"], TOP) for r in subset)
        rr = [reciprocal_rank(r["ranked"][method], r["relevant"]) for r in subset]
        return {"n": n, "hit1": h1, "hit1_ci": ci95(h1, n), "hit5": h5, "hit5_ci": ci95(h5, n),
                "mrr": _mrr(rr)}  # fmt: skip

    answerable = [r for r in rows if r["kind"] in ANSWERABLE]
    out: dict[str, Any] = {"overall": {m: scored(answerable, m) for m in METHODS}, "by_kind": {}}
    for kind in ANSWERABLE:
        subset = [r for r in rows if r["kind"] == kind]
        out["by_kind"][kind] = {m: scored(subset, m) for m in METHODS}

    classes = [r for r in rows if r["kind"] == "class"]
    out["class"] = {
        "queries": [
            {
                "id": r["id"],
                "query": r["query"],
                "cls": r["cls"],
                "base_rate": round(len(r["relevant"]) / collection, 4),
                **{m: round(precision_at(r["ranked"][m], r["relevant"], TOP), 4) for m in METHODS},
            }
            for r in classes
        ],
        "mean": {
            m: _mrr([precision_at(r["ranked"][m], r["relevant"], TOP) for r in classes])
            for m in METHODS
        },
        "base_rate": round(statistics.fmean(len(r["relevant"]) / collection for r in classes), 4)
        if classes
        else 0.0,
    }

    off = sorted(r["top_similarity"] for r in rows if r["kind"] == "no_answer")
    on = sorted(r["top_similarity"] for r in answerable)
    out["no_answer"] = {
        "n": len(off),
        "off_topic": {"median": statistics.median(off), "max": off[-1]} if off else None,
        "answerable": {"median": statistics.median(on), "min": on[0]} if on else None,
        "below_every_answerable": sum(s < on[0] for s in off) if off and on else 0,
    }
    return out


# --- The report ------------------------------------------------------------------------------


def _pct(s: dict[str, Any], field: str) -> str:
    return pct_ci(s[field], s["n"])


def _mrr_text(m: dict[str, Any]) -> str:
    return f"{m['mean']:.2f} ({m['ci'][0]:.2f}–{m['ci'][1]:.2f})"


def render(
    summary: dict[str, Any],
    rows: Sequence[dict[str, Any]],
    names: dict[str, str],
    *,
    model: str,
    collection: int,
    measured: str,
) -> str:
    o = summary["overall"]
    header = "| " + " | ".join(METHOD_NAMES[m] for m in METHODS) + " |"
    rule = " --- |" * len(METHODS)
    lines = [
        "# Explainer search: retrieval eval",
        "",
        f"{measured} · embeddings `{model}` · {collection:,} explainers · "
        f"{len(rows)} queries from `evals/datasets/retrieval.jsonl`",
        "",
        "Does the ask agent's `search_explainers` tool put the right explainer in the 5 it "
        "returns? The agent's search looks up any E-number in the question exactly, then adds "
        "the nearest explainers by vector (cosine, exact, on the committed vectors). Vector "
        "alone is how the tool worked before the E-number lookup; keyword is BM25 on the same "
        "text; hybrid fuses vector and keyword (reciprocal rank fusion). Generated by "
        "`uv run python -m evals.runners.retrieval_eval`.",
        "",
        INTERVAL_NOTE + " MRR ranges are a bootstrap over queries.",
        "",
        f"## Queries with an answer ({o['agent']['n']})",
        "",
        "| " + header,
        "| --- |" + rule,
        "| Right explainer in the top 5 | "
        + " | ".join(_pct(o[m], "hit5") for m in METHODS)
        + " |",
        "| Right explainer first | " + " | ".join(_pct(o[m], "hit1") for m in METHODS) + " |",
        "| MRR@10 | " + " | ".join(_mrr_text(o[m]["mrr"]) for m in METHODS) + " |",
        "",
        "## By kind of query: right explainer in the top 5",
        "",
        "| Kind | n " + header,
        "| --- | ---: |" + rule,
    ]
    for kind, s in summary["by_kind"].items():
        lines.append(
            f"| {KIND_NAMES[kind]} | {s['agent']['n']} | "
            + " | ".join(_pct(s[m], "hit5") for m in METHODS)
            + " |"
        )
    c = summary["class"]
    lines += [
        "",
        "## What it does: share of the top 5 in the asked-for class",
        "",
        "One query per Open Food Facts additive class; a result counts when the additive is in "
        f"that class. Picking 5 at random would score about {100 * c['base_rate']:.0f}%, the "
        "classes' average share of the collection. No class query holds an E-number, so the "
        "agent's search and vector alone agree.",
        "",
        "Mean precision@5: "
        + ", ".join(f"{METHOD_NAMES[m]} {_mrr_text(c['mean'][m])}" for m in METHODS)
        + ".",
        "",
        "| Query | Class | At random " + header,
        "| --- | --- | ---: |" + " ---: |" * len(METHODS),
    ]
    for q in c["queries"]:
        lines.append(
            f"| {q['query']} | `{q['cls']}` | {100 * q['base_rate']:.0f}% | "
            + " | ".join(f"{100 * q[m]:.0f}%" for m in METHODS)
            + " |"
        )
    na = summary["no_answer"]
    if na["off_topic"] and na["answerable"]:
        lines += [
            "",
            "## Off-topic questions",
            "",
            "Vector search always returns 5 results; the agent decides what to use. Could a "
            "similarity cut-off tell an off-topic question apart? Best cosine similarity:",
            "",
            f"- answerable queries: median {na['answerable']['median']:.3f}, lowest "
            f"{na['answerable']['min']:.3f};",
            f"- off-topic queries ({na['n']}): median {na['off_topic']['median']:.3f}, highest "
            f"{na['off_topic']['max']:.3f}.",
            f"- {na['below_every_answerable']} of {na['n']} off-topic queries score below every "
            "answerable one.",
        ]
    misses = [
        r
        for r in rows
        if r["kind"] in ANSWERABLE and not hit_at(r["ranked"]["agent"], r["relevant"], TOP)
    ]
    lines += [
        "",
        f"## Every miss by the agent's search ({len(misses)})",
        "",
        "The right explainer was not in the agent's top 5.",
        "",
        "| Id | Query | Right answer | The agent's first result | Keyword's first result |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in misses:
        right = ", ".join(names[i] for i in r["relevant"][:2]) + (
            "…" if len(r["relevant"]) > 2 else ""
        )
        lines.append(
            f"| {r['id']} | {r['query']} | {right} | {names[r['ranked']['agent'][0]]} | "
            f"{names[r['ranked']['keyword'][0]]} |"
        )
    authors = Counter(r["written_by"] for r in rows)
    lines += [
        "",
        "## Who wrote the queries and answers",
        "",
        *(f"- {who}: {n} queries" for who, n in sorted(authors.items())),
        "",
        "Name, E-number and misspelt-name queries take their answers from the data. Class "
        "queries were phrased by Claude Code, with answers from Open Food Facts' classes. The "
        "descriptive and off-topic queries, and their answers, were written by Claude Code and "
        "not checked by a person; all are in the dataset to be audited.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieval eval for the explainer search.")
    parser.add_argument("--limit", type=int, required=True, help="most queries to embed")
    parser.add_argument("--yes", action="store_true", help="send queries to Voyage")
    parser.add_argument("--label", default="retrieval", help="report file name")
    args = parser.parse_args(argv)

    import sys

    sys.path.insert(0, str(ROOT))
    from api.app.config import embedding_price_per_mtok, get_settings
    from api.app.embeddings import Voyage

    dataset = load_dataset()
    explainers = load_explainers()
    models = {e["model"] for e in explainers}
    settings = get_settings()
    model = settings.embeddings_model
    if models != {model}:
        raise SystemExit(f"Explainers were embedded with {models}; queries would use {model}.")
    dim = len(explainers[0]["embedding"])
    key = settings.embeddings_api_key.get_secret_value() if settings.embeddings_api_key else None
    voyage = Voyage(key, model)
    vectors = query_vectors(
        [item["query"] for item in dataset],
        model=model,
        dim=dim,
        embed=lambda batch: voyage.embed(batch, input_type="query"),
        price_per_mtok=embedding_price_per_mtok(model),
        limit=args.limit,
        yes=args.yes,
    )
    if vectors is None:
        return 0
    rows = run(dataset, explainers, vectors)
    summary = summarize(rows, len(explainers))
    names = {e["id"]: e["name"] for e in explainers}
    measured = datetime.now(UTC).isoformat(timespec="seconds")
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / f"{args.label}.md").write_text(
        render(summary, rows, names, model=model, collection=len(explainers), measured=measured),
        "utf-8",
    )
    detail = [
        {"id": r["id"], "kind": r["kind"], "query": r["query"], "relevant": r["relevant"],
         "top_similarity": r["top_similarity"],
         **{m: r["ranked"][m][:TOP] for m in METHODS}}
        for r in rows
    ]  # fmt: skip
    (RESULTS / f"{args.label}.json").write_text(
        json.dumps(
            {"measured": measured, "model": model, "summary": summary, "queries": detail},
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        "utf-8",
    )
    o = summary["overall"]
    print(
        "Top 5: "
        + ", ".join(f"{m} {100 * o[m]['hit5'] / o[m]['n']:.0f}%" for m in METHODS)
        + f" of {o['vector']['n']}. Report: evals/results/{args.label}.md"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
