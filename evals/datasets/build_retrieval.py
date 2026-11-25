"""Build the retrieval eval's query set: evals/datasets/retrieval.jsonl.

    uv run python -m evals.datasets.build_retrieval

Each line is one query with the explainers that answer it (`relevant`, explainer ids). The
explainers are the 1,019 the ask agent's `search_explainers` tool searches
(pipeline/enrich/outputs/explainer_embeddings.parquet). Six kinds of query:

- name: "What is carrageenan?". Phrasing from templates, the answer from the data.
- e_number: "What is E407?". The additive's E-number from Open Food Facts' taxonomy.
- misspelling: the name with two letters swapped ("carraegenan").
- class: "something that keeps oil and water mixed". The phrasing was written by Claude Code;
  the answer is every additive Open Food Facts puts in that class (here, emulsifiers).
- descriptive: "baking soda", "the red dye in candy". Phrasing and answers both written by
  Claude Code and not checked by a person; every one is listed in the dataset to be audited.
- no_answer: off-topic questions nothing in the collection answers.

Answers are fair to how the data is split: Open Food Facts lists an additive and its
narrower forms separately, each with an explainer (E322 Lecithins and E322i Lecithin), so a
parent or child counts as right. Siblings do not: E160a beta-carotene does not answer for
E160b annatto.

Name, E-number and misspelling queries are spread across how common each additive or
ingredient is (by the number of US products that list it), from citric acid down, so the set
is not only well-known names. Needs the snapshot's taxonomy (data/raw/<date>/additives.json,
read only) and the dbt build (data/labellens.duckdb) for those counts.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXPLAINERS = ROOT / "pipeline" / "enrich" / "outputs" / "explainer_embeddings.parquet"
DUCKDB_PATH = ROOT / "data" / "labellens.duckdb"
OUTPUT = ROOT / "evals" / "datasets" / "retrieval.jsonl"

PER_KIND = {"name": 20, "e_number": 30, "misspelling": 15}  # name and misspelling: per kind

NAME_TEMPLATES = ("What is {}?", "{}", "Why is {} in food?", "What does {} do?")
E_NUMBER_TEMPLATES = ("What is {}?", "{}", "What does {} do in food?")

# Phrasing written by Claude Code; the answer is every additive in the class.
CLASS_QUERIES = {
    "en:colour": "an additive that colours food",
    "en:emulsifier": "something that keeps oil and water mixed",
    "en:thickener": "what thickens sauces and desserts",
    "en:stabiliser": "an additive that keeps a texture stable",
    "en:preservative": "an additive that stops food going off",
    "en:antioxidant": "what stops fats from going rancid",
    "en:sweetener": "a sugar substitute",
    "en:humectant": "something that keeps food moist",
    "en:sequestrant": "an additive that binds metals in food",
    "en:carrier": "a substance used to carry flavours or colours",
}

# Phrasing and answers both written by Claude Code, not checked by a person.
DESCRIPTIVE: list[tuple[str, list[str]]] = [
    ("baking soda", ["en:e500ii"]),
    ("vitamin C added to drinks", ["en:e300", "en:vitamin-c"]),
    ("MSG", ["en:e621"]),
    ("the red dye in candy", ["en:e129", "en:e124", "en:e120", "en:e127", "en:e122"]),
    ("yellow food colouring", ["en:e102", "en:e110", "en:e104", "en:e100", "en:e160a"]),
    ("the sweetener in diet soda", ["en:e951", "en:e950", "en:e955"]),
    ("the preservative in soft drinks", ["en:e211", "en:e202"]),
    ("a thickener made from seaweed", ["en:e407", "en:e406", "en:e401", "en:e407a"]),
    ("a salt substitute", ["en:e508"]),
    ("the gas that makes drinks fizzy", ["en:e290"]),
    ("vitamin E used as an antioxidant", ["en:e306", "en:e307"]),
    ("caramel colour in cola", ["en:e150d", "en:e150a"]),
    ("the acid in cola", ["en:e338"]),
    ("soy lecithin", ["en:e322"]),
    ("a thickener made from beans", ["en:e412", "en:e410"]),
    ("nitrite in bacon", ["en:e250", "en:e249", "en:e252"]),
    ("sulfites in wine and dried fruit", ["en:e220", "en:e223", "en:e224", "en:e228"]),
    ("lye used to make pretzels", ["en:e524"]),
    ("anti-foaming agent in frying oil", ["en:e900"]),
    ("cellulose made from wood pulp", ["en:e460"]),
    ("a sugar alcohol in sugar-free gum", ["en:e420", "en:e967", "en:e965", "en:e953"]),
    ("high fructose corn syrup", ["en:glucose-fructose-syrup", "en:corn-syrup"]),
    ("the stimulant in coffee and energy drinks", ["en:caffeine"]),
    ("protein from milk used in shakes", ["en:whey-protein", "en:whey-protein-isolate", "en:whey"]),
    ("white colouring in sweets and icing", ["en:e171", "en:e170"]),
]

NO_ANSWER = [
    "What is the capital of France?",
    "How do I fix a flat bicycle tyre?",
    "What is a blockchain?",
    "Who wrote Hamlet?",
    "How tall is Mount Everest?",
    "What is the best laptop for students?",
    "How do I reset my email password?",
    "When did the first moon landing happen?",
    "What is the offside rule in football?",
    "How many planets are in the solar system?",
]

_E_ID = re.compile(r"^en:e(\d+)([a-z]*)$")


def e_number(additive_id: str) -> str | None:
    """'en:e322i' -> 'E322i' (as the pipeline labels it); None for an id without one."""
    match = _E_ID.match(additive_id)
    return f"E{match.group(1)}{match.group(2)}" if match else None


_SUFFIX = re.compile(r"^([a-h]?)((?:i|ii|iii|iv|v|vi|vii|viii|ix|x)?)$")


def _path(additive_id: str) -> tuple[str, str, str] | None:
    """'en:e160aii' -> ('160', 'a', 'ii'): number, then letter, then roman numeral."""
    match = _E_ID.match(additive_id)
    if not match:
        return None
    suffix = _SUFFIX.match(match.group(2))
    if suffix is None:
        return match.group(1), match.group(2), ""
    return match.group(1), suffix.group(1), suffix.group(2)


def _related(a: tuple[str, str, str], b: tuple[str, str, str]) -> bool:
    """One is the other, or its parent, or its child (E160 > E160a > E160aii); not siblings."""
    if a[0] != b[0]:
        return False
    narrower_or_same = all(x in ("", y) for x, y in zip(a[1:], b[1:], strict=True))
    broader_or_same = all(y in ("", x) for x, y in zip(a[1:], b[1:], strict=True))
    return narrower_or_same or broader_or_same


def groups(ids: list[str]) -> dict[str, list[str]]:
    """Each id with every id that answers for it: an additive with its parents and children
    (E322 Lecithins and E322i Lecithin), not its siblings (E160a beta-carotene is not E160b
    annatto). Anything else answers only for itself."""
    paths = {i: p for i in ids if (p := _path(i))}
    out = {}
    for i in ids:
        p = paths.get(i)
        out[i] = sorted(j for j, q in paths.items() if _related(p, q)) if p else [i]
    return out


def misspell(name: str) -> str:
    """Swap two neighbouring letters near the middle: deterministic, and always a change."""
    text = name.lower()
    letters = [i for i in range(len(text) - 1) if text[i].isalpha() and text[i + 1].isalpha()]
    for i in sorted(letters, key=lambda i: abs(i - len(text) // 2)):
        if text[i] != text[i + 1]:
            return text[:i] + text[i + 1] + text[i] + text[i + 2 :]
    return text + text[-1]  # no two different letters side by side: double the last one


def spread(items: list[Any], n: int, offset: int = 0) -> list[Any]:
    """n items evenly spaced through a list (most common first), starting `offset` in."""
    if n <= 0 or not items:
        return []
    step = len(items) / n
    picked = []
    for k in range(n):
        index = (int(k * step) + offset) % len(items)
        if items[index] not in picked:
            picked.append(items[index])
    return picked


def expand(ids: list[str], group_of: dict[str, list[str]]) -> list[str]:
    out: list[str] = []
    for i in ids:
        for j in group_of.get(i, []):
            if j not in out:
                out.append(j)
    return out


def build(
    explainers: list[dict[str, str]],
    taxonomy: dict[str, Any],
    counts: dict[str, int],
) -> list[dict[str, Any]]:
    """The query set from the explainers (kind, id, name), the taxonomy and product counts."""
    ids = [e["id"] for e in explainers]
    known = set(ids)
    name_of = {e["id"]: e["name"] for e in explainers}
    group_of = groups(ids)

    def common_first(kind: str) -> list[str]:
        chosen = [e["id"] for e in explainers if e["kind"] == kind]
        return sorted(chosen, key=lambda i: (-counts.get(i, 0), i))

    additives, ingredients = common_first("additive"), common_first("ingredient")
    rows: list[dict[str, Any]] = []

    def add(kind: str, query: str, relevant: list[str], written_by: str, **extra: Any) -> None:
        rows.append({
            "id": f"{kind}-{sum(r['kind'] == kind for r in rows) + 1:02d}", "kind": kind,
            "query": query, "relevant": relevant, "written_by": written_by, **extra,
        })  # fmt: skip

    # A few explainers are named only by their E-number ("E440a"): those are e_number queries.
    named = [i for i in additives if not re.match(r"^E\s?\d", name_of[i])]
    for pool, offset in ((named, 0), (ingredients, 0)):
        for k, i in enumerate(spread(pool, PER_KIND["name"], offset)):
            add("name", NAME_TEMPLATES[k % len(NAME_TEMPLATES)].format(name_of[i]),
                group_of[i], "data", target=i)  # fmt: skip
    numbered = [i for i in additives if e_number(i)]
    for k, i in enumerate(spread(numbered, PER_KIND["e_number"], offset=3)):
        add("e_number", E_NUMBER_TEMPLATES[k % len(E_NUMBER_TEMPLATES)].format(e_number(i)),
            group_of[i], "data", target=i)  # fmt: skip
    for pool in (named, ingredients):
        for i in spread(pool, PER_KIND["misspelling"], offset=7):
            add("misspelling", misspell(name_of[i]), group_of[i], "data", target=i)

    def classes_of(additive_id: str) -> list[str]:
        entry = taxonomy.get(additive_id, {})
        text: str = (entry.get("additives_classes") or {}).get("en") or ""
        return [c.strip() for c in text.split(",") if c.strip()]

    for cls, query in CLASS_QUERIES.items():
        members = [i for i in additives if cls in classes_of(i)]
        if len(members) >= 5:
            add("class", query, sorted(members), "Claude Code (phrasing); data (answers)", cls=cls)

    for query, expected in DESCRIPTIVE:
        present = [i for i in expected if i in known]
        if not present:
            raise ValueError(f"No explainer for any answer to {query!r}: {expected}")
        add("descriptive", query, expand(present, group_of), "Claude Code")

    for query in NO_ANSWER:
        add("no_answer", query, [], "Claude Code")
    return rows


def main() -> int:
    import duckdb

    raw = sorted(p for p in (ROOT / "data" / "raw").iterdir() if (p / "additives.json").exists())
    if not raw:
        raise SystemExit("No taxonomy under data/raw. Run the snapshot with --taxonomy-only first.")
    taxonomy = json.loads((raw[-1] / "additives.json").read_text("utf-8"))
    with duckdb.connect() as con:
        explainers = [
            {"kind": k, "id": i, "name": n}
            for k, i, n in con.execute(
                "select kind, id, name from read_parquet(?) order by kind, id", [str(EXPLAINERS)]
            ).fetchall()
        ]
    with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
        counts = dict(con.execute(
            "select additive_id, product_count from dim_additives union all "
            "select ingredient_id, product_count from dim_ingredients"
        ).fetchall())  # fmt: skip
    rows = build(explainers, taxonomy, counts)
    OUTPUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")
    by_kind: dict[str, int] = defaultdict(int)
    for r in rows:
        by_kind[r["kind"]] += 1
    print(f"Wrote {len(rows)} queries to {OUTPUT.relative_to(ROOT)}: {dict(by_kind)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
