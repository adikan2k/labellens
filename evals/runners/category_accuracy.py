"""Category eval: the model's categories against your 200 hand labels.

    uv run python -m evals.runners.category_accuracy --limit 200              # estimate
    uv run python -m evals.runners.category_accuracy --limit 200 --yes        # run
    uv run python -m evals.runners.category_accuracy --limit 200 --yes --name-only
    uv run python -m evals.runners.category_accuracy --limit 200 --yes --model eval
    uv run python -m evals.runners.category_accuracy --limit 1000 --yes --tagged-sample 1000

Gold labels: evals/datasets/category_gold.csv (scripts/label.py). The model sees exactly what
the fill sends (int_category_inputs), through the same prompt and validation, but on the
Messages API so the run takes seconds. Results are cached in evals/cache/categories.jsonl
(committed), so a rerun costs nothing.

Reported: accuracy (an invalid answer counts as wrong), accuracy on the "dev" and "test"
halves (split by a hash of the barcode; prompt changes are tuned on dev errors only),
accuracy for gold products that Open Food Facts' tags place and those they do not, the
tag mapping's own accuracy on the products it places (the baseline), per-category recall
and precision, and the most common confusions.

--tagged-sample N instead compares the model, given only the name and brand, with the tag
category of N products that have one: a larger, cheaper check of agreement, not accuracy.

--name-only drops the ingredients, which most products being filled do not have; the gold
sample was drawn from products with ingredients, so this is the closer estimate for them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pipeline.enrich import categories, core

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evals" / "datasets" / "category_gold.csv"
CACHE = ROOT / "evals" / "cache" / "categories.jsonl"
RESULTS = ROOT / "evals" / "results"
TARGET = 0.90


@dataclass
class Scores:
    n: int
    correct: int
    accuracy: float
    invalid: int
    per_category: dict[str, dict[str, float | int]]
    confusions: list[tuple[str, str, int]]


def score(pairs: Sequence[tuple[str, str | None]]) -> Scores:
    """pairs: (truth, prediction); a None prediction (invalid) counts as wrong."""
    n = len(pairs)
    correct = sum(1 for truth, pred in pairs if pred == truth)
    labels = sorted({t for t, _ in pairs} | {p for _, p in pairs if p})
    per_category: dict[str, dict[str, float | int]] = {}
    for label in labels:
        support = sum(1 for t, _ in pairs if t == label)
        predicted = sum(1 for _, p in pairs if p == label)
        hits = sum(1 for t, p in pairs if t == label and p == label)
        per_category[label] = {
            "support": support,
            "predicted": predicted,
            "recall": round(hits / support, 3) if support else 0.0,
            "precision": round(hits / predicted, 3) if predicted else 0.0,
        }
    confusions = Counter((t, p or "(invalid)") for t, p in pairs if p != t)
    return Scores(
        n=n,
        correct=correct,
        accuracy=round(correct / n, 4) if n else 0.0,
        invalid=sum(1 for _, p in pairs if p is None),
        per_category=per_category,
        confusions=[(t, p, c) for (t, p), c in confusions.most_common(15)],
    )


def half(code: str) -> str:
    """A fixed split of the gold set: prompt changes are tuned on dev errors only."""
    return "dev" if int(hashlib.md5(code.encode()).hexdigest(), 16) % 2 == 0 else "test"


def load_gold(path: Path = GOLD) -> dict[str, str]:
    if not path.exists():
        raise SystemExit(
            f"{path} does not exist yet. Label the sample: uv run python scripts/label.py"
        )
    with path.open(encoding="utf-8", newline="") as f:
        return {row["code"]: row["category_id"] for row in csv.DictReader(f)}


@dataclass
class Report:
    label: str
    model: str
    prompt_version: str
    inputs: str
    measured_at: str
    overall: Scores
    halves: dict[str, Scores] = field(default_factory=dict)
    by_tags: dict[str, Scores] = field(default_factory=dict)
    tag_baseline: Scores | None = None
    missing: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    target: float = TARGET


def _table(s: Scores) -> str:
    return f"{s.accuracy:.1%} ({s.correct}/{s.n})"


def to_markdown(report: Report, names: dict[str, str]) -> str:
    o = report.overall
    verdict = "meets" if o.accuracy >= report.target else "misses"
    lines = [
        f"# Category accuracy: {report.label}",
        "",
        f"Measured {report.measured_at}: `{report.model}`, prompt `{report.prompt_version}`, "
        f"inputs: {report.inputs}. Cost ${report.cost_usd:.4f} (0 when every answer was "
        "cached).",
        "",
        "| | Accuracy |",
        "| --- | ---: |",
        f"| **All gold products** | **{_table(o)}** |",
    ]
    for name, s in report.halves.items():
        lines.append(f"| {name} half | {_table(s)} |")
    for name, s in report.by_tags.items():
        lines.append(f"| {name} | {_table(s)} |")
    if report.tag_baseline:
        lines.append(
            f"| Baseline: Open Food Facts' tags, where they give a category | "
            f"{_table(report.tag_baseline)} |"
        )
    lines += [
        "",
        f"Target: {report.target:.0%}. This run **{verdict}** it. "
        f"Invalid answers (counted wrong): {o.invalid}.",
    ]
    if report.missing:
        lines.append(f"Gold products not in the current data (skipped): {len(report.missing)}.")
    lines += [
        "",
        "## Most common confusions",
        "",
        "| Gold label | Model said | Count |",
        "| --- | --- | ---: |",
        *[f"| {names.get(t, t)} | {names.get(p, p)} | {c} |" for t, p, c in o.confusions],
        "",
        "## By category",
        "",
        "| Category | Gold products | Recall | Precision |",
        "| --- | ---: | ---: | ---: |",
        *[
            f"| {names.get(k, k)} | {v['support']} | {v['recall']:.0%} | {v['precision']:.0%} |"
            for k, v in sorted(o.per_category.items(), key=lambda kv: -int(kv[1]["support"]))
        ],
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from api.app.config import get_settings, price_per_mtok

    parser = argparse.ArgumentParser(description="Category accuracy against the gold labels.")
    parser.add_argument("--limit", type=int, required=True, help="most products to send")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--model", choices=["default", "eval"], default="default")
    parser.add_argument("--name-only", action="store_true", help="leave out the ingredients")
    parser.add_argument("--tagged-sample", type=int, help="agreement with tags on N products")
    parser.add_argument("--duckdb", type=Path, default=categories.DUCKDB_PATH)
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    args = parser.parse_args(argv)

    settings = get_settings()
    model = settings.model_default if args.model == "default" else settings.model_eval
    # Haiku 5.5 allows thinking off at low effort; the eval model (Sonnet 5.5) does not.
    call = core.CallSettings(model=model, thinking_off=args.model == "default")
    task = categories.CategoryTask()
    names = task.leaves

    import duckdb

    if args.tagged_sample:
        with duckdb.connect(str(args.duckdb), read_only=True) as con:
            truth = dict(
                con.execute(
                    "select code, tag_category from int_category_inputs where tag_category is not "
                    "null order by md5(code || ':tagged-sample-v1') limit ?",
                    [args.tagged_sample],
                ).fetchall()
            )
        name_only, label_suffix = True, f"tagged{args.tagged_sample}"
    else:
        truth = load_gold()
        name_only, label_suffix = args.name_only, ("name-only" if args.name_only else "full")

    items = categories.load_items(
        args.duckdb, codes=list(truth), untagged_only=False, name_only=name_only
    )
    summary = core.run(
        task,
        items,
        client_factory=categories.client_factory,
        settings=call,
        store=core.OutputStore(CACHE),
        prices=price_per_mtok(model),
        limit=args.limit,
        yes=args.yes,
        batch=False,
    )
    if summary.uncached and not args.yes:
        return 0

    keys = {i.ref: core.cache_key(task, call, i.payload) for i in items}
    answers = {r["key"]: r["value"] for r in core.OutputStore(CACHE).load()}
    predicted = {code: answers.get(key) for code, key in keys.items()}
    found = [c for c in truth if c in predicted]
    pairs = [(truth[c], predicted[c]) for c in found]

    report = Report(
        label=f"{model}-{label_suffix}",
        model=model,
        prompt_version=task.prompt_version,
        inputs="name and brand only" if name_only else "name, brand and ingredients",
        measured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        overall=score(pairs),
        missing=[c for c in truth if c not in predicted],
        cost_usd=round(summary.cost, 4),
    )
    if not args.tagged_sample:
        report.halves = {
            h: score([(truth[c], predicted[c]) for c in found if half(c) == h])
            for h in ("dev", "test")
        }
        with duckdb.connect(str(args.duckdb), read_only=True) as con:
            tags = dict(
                con.execute(
                    "select code, tag_category from int_category_inputs where code in "
                    "(select unnest(?))",
                    [found],
                ).fetchall()
            )
        tagged = [c for c in found if tags.get(c)]
        report.by_tags = {
            "Gold products Open Food Facts' tags place": score(
                [(truth[c], predicted[c]) for c in tagged]
            ),
            "Gold products they do not (what the fill is for)": score(
                [(truth[c], predicted[c]) for c in found if not tags.get(c)]
            ),
        }
        report.tag_baseline = score([(truth[c], tags[c]) for c in tagged])

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.out_dir / f"category_accuracy_{report.label}"
    stem.with_suffix(".json").write_text(json.dumps(asdict(report), indent=2) + "\n", "utf-8")
    text = to_markdown(report, names)
    stem.with_suffix(".md").write_text(text, "utf-8", newline="\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
