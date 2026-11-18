"""Embed the explainers for the ask agent's search_explainers tool (Voyage, decision 0001).

    uv run python -m pipeline.enrich.embeddings --limit 2000            # estimate only
    uv run python -m pipeline.enrich.embeddings --limit 2000 --yes      # send

One vector per explainer: every additive with one, and every ingredient with its own (an
ingredient that is an additive shares the additive's). The text embedded is
"Name: explainer". Vectors are cached by a hash of model, dimension and text, so a rerun
sends only new or changed texts and costs nothing otherwise.

Output: pipeline/enrich/outputs/explainer_embeddings.parquet (committed, about 4 MB):
kind, id, name, text, key, model, embedding (FLOAT[1024]). The serving loader reads it into
serving.explainers (pgvector).
"""

from __future__ import annotations

import argparse
import hashlib
import math
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.app.embeddings import DIMENSION, MAX_BATCH, Voyage
from pipeline.enrich.core import OUTPUTS

ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = ROOT / "data" / "labellens.duckdb"
OUTPUT = OUTPUTS / "explainer_embeddings.parquet"
BATCH = 128
CHARS_PER_TOKEN = 3.0  # conservative for English; Voyage bills about 4

TEXTS_SQL = """
select 'additive' as kind, additive_id as id, name, explainer as text
from dim_additives where explainer is not null
union all
select 'ingredient', ingredient_id, name, explainer
from dim_ingredients
where explainer is not null
  and ingredient_id not in (select additive_id from dim_additives)
order by 1, 2
"""

Log = Callable[[str], None]


@dataclass
class Summary:
    cached: int = 0
    sent: int = 0
    tokens: int = 0
    estimated_cost: float = 0.0
    cost: float = 0.0


def document(name: str, text: str) -> str:
    return f"{name}: {text}"


def key(model: str, text: str) -> str:
    return hashlib.sha256(f"{model}|{DIMENSION}|document|{text}".encode()).hexdigest()[:32]


def load_texts(duckdb_path: Path = DUCKDB_PATH) -> list[dict[str, str]]:
    import duckdb

    with duckdb.connect(str(duckdb_path), read_only=True) as con:
        rows = con.execute(TEXTS_SQL).fetchall()
    return [{"kind": k, "id": i, "name": n, "text": t} for k, i, n, t in rows]


def load_store(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    import duckdb

    with duckdb.connect() as con:
        cursor = con.execute("select * from read_parquet(?)", [str(path)])
        names = [d[0] for d in cursor.description]
        return {
            row[names.index("key")]: dict(zip(names, row, strict=True)) for row in cursor.fetchall()
        }


def save_store(path: Path, rows: list[dict[str, Any]]) -> None:
    import duckdb

    rows = sorted(rows, key=lambda r: (r["kind"], r["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, duckdb.connect() as con:
        con.execute(
            f"create table e (kind varchar, id varchar, name varchar, text varchar, "
            f"key varchar, model varchar, embedding float[{DIMENSION}])"
        )
        con.executemany(
            "insert into e values (?, ?, ?, ?, ?, ?, ?)",
            [[r["kind"], r["id"], r["name"], r["text"], r["key"], r["model"], r["embedding"]]
             for r in rows],
        )  # fmt: skip
        staged = Path(tmp) / "e.parquet"
        con.execute("copy e to ? (format parquet, compression zstd)", [str(staged)])
        staged.replace(path)


def run(
    texts: list[dict[str, str]],
    *,
    voyage_factory: Callable[[], Voyage],
    model: str,
    price_per_mtok: float,
    store: Path = OUTPUT,
    limit: int,
    yes: bool,
    log: Log = print,
) -> Summary:
    summary = Summary()
    known = load_store(store)
    rows: list[dict[str, Any]] = []
    todo: list[tuple[dict[str, str], str, str]] = []
    for item in texts:
        doc = document(item["name"], item["text"])
        k = key(model, doc)
        if k in known:
            rows.append({**known[k], "kind": item["kind"], "id": item["id"], "name": item["name"]})
        else:
            todo.append((item, doc, k))
    summary.cached = len(rows)
    todo = todo[: max(limit, 0)]
    if not todo:
        if len(rows) != len(known):
            save_store(store, rows)  # drop vectors for explainers that no longer exist
        log(f"{summary.cached:,} explainers embedded already, 0 to send: no calls, $0.00.")
        return summary

    est_tokens = math.ceil(sum(len(doc) for _, doc, _ in todo) / CHARS_PER_TOKEN)
    summary.estimated_cost = est_tokens * price_per_mtok / 1e6
    log(
        f"{summary.cached:,} explainers embedded already; sending {len(todo):,} "
        f"(--limit {limit:,}) to {model} in {math.ceil(len(todo) / BATCH)} requests. "
        f"Estimated {est_tokens:,} tokens: about ${summary.estimated_cost:.4f} "
        "(Voyage's free tokens cover this)."
    )
    if not yes:
        log("Nothing sent. Add --yes to run it.")
        return summary

    voyage = voyage_factory()
    for start in range(0, len(todo), min(BATCH, MAX_BATCH)):
        chunk = todo[start : start + BATCH]
        embedded = voyage.embed([doc for _, doc, _ in chunk], input_type="document")
        summary.tokens += embedded.tokens
        for (item, _doc, k), vector in zip(chunk, embedded.vectors, strict=True):
            rows.append({**item, "key": k, "model": model, "embedding": vector})
        summary.sent += len(chunk)
        save_store(store, rows)  # after every batch, so an interruption loses nothing paid for
    summary.cost = summary.tokens * price_per_mtok / 1e6
    log(f"Done: {summary.sent:,} embedded, {summary.tokens:,} tokens: ${summary.cost:.4f}.")
    return summary


def main(argv: list[str] | None = None) -> int:
    from api.app.config import embedding_price_per_mtok, get_settings

    parser = argparse.ArgumentParser(description="Embed the explainers with Voyage.")
    parser.add_argument("--limit", type=int, required=True, help="most explainers to send")
    parser.add_argument("--yes", action="store_true", help="send (uses Voyage tokens)")
    parser.add_argument("--duckdb", type=Path, default=DUCKDB_PATH)
    args = parser.parse_args(argv)

    settings = get_settings()
    model = settings.embeddings_model
    key_value = (
        settings.embeddings_api_key.get_secret_value() if settings.embeddings_api_key else None
    )

    def factory() -> Voyage:
        if not key_value:
            raise SystemExit("EMBEDDINGS_API_KEY is not set (.env). Nothing was sent.")
        return Voyage(key_value, model)

    texts = load_texts(args.duckdb)
    print(f"{len(texts):,} explainers to embed.")
    run(
        texts,
        voyage_factory=factory,
        model=model,
        price_per_mtok=embedding_price_per_mtok(model),
        store=OUTPUT,
        limit=args.limit,
        yes=args.yes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
