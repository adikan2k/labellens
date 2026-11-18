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
and precision, and the most common confusions. Every accuracy carries a 95% Wilson score
interval (evals/runners/stats.py).

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

from evals.runners.stats import INTERVAL_NOTE, ci95, pct_ci
from pipeline.enrich import categories, core

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "evals" / "datasets" / "category_gold.csv"
# Labels written by Claude Opus 5.5 from the same sample and category definitions, without
# seeing the evaluated model's answers. An AI's labels, so reports say so: agreement with a
# stronger model, not accuracy against a person.
SILVER = ROOT / "evals" / "datasets" / "category_silver_opus.csv"
LABELS = {
    "gold": (GOLD, "200 products labelled by hand"),
    "silver": (SILVER, "200 products labelled by Claude Opus 5.5 (an AI model, not a person)"),
    "audit": (
        ROOT / "evals" / "datasets" / "category_audit_human.csv",
        "30 of the 200 labelled by hand, blind to the AI labels (scripts/audit_labels.py)",
    ),
}
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
    ci95: list[float] = field(default_factory=lambda: [0.0, 1.0])  # Wilson, [low, high]


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
        ci95=ci95(correct, n),
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
    against: str = "gold"  # "gold": your labels (accuracy); "tags": OFF's tags (agreement)
    labels: str = ""  # who made the labels


def _table(s: Scores) -> str:
    return f"{s.correct}/{s.n}: {pct_ci(s.correct, s.n, digits=1)}"


def to_markdown(report: Report, names: dict[str, str]) -> str:
    o = report.overall
    gold = report.against == "gold"
    truth = "Label" if gold else "Tag category"
    verdict = "meets" if o.accuracy >= report.target else "misses"
    lines = [
        f"# Category {'accuracy' if gold else 'agreement with tags'}: {report.label}",
        "",
        f"Measured {report.measured_at}: `{report.model}`, prompt `{report.prompt_version}`, "
        f"inputs: {report.inputs}. Cost ${report.cost_usd:.4f} (0 when every answer was "
        "cached).",
        *(["", f"Labels: {report.labels}."] if report.labels else []),
        "",
        "| | Accuracy |" if gold else "| | Agreement |",
        "| --- | ---: |",
        f"| **All {'labelled products' if gold else 'sampled products'}** | **{_table(o)}** |",
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
    lines += ["", INTERVAL_NOTE, ""]
    if gold:
        lines.append(
            f"Target: {report.target:.0%}. This run **{verdict}** it. "
            f"Invalid answers (counted wrong): {o.invalid}."
        )
    else:
        lines.append(
            "Agreement, not accuracy: Open Food Facts' tags and our tag mapping make mistakes "
            "of their own, so a disagreement is not always the model's error. The 90% target "
            f"applies to the gold labels. Invalid answers: {o.invalid}."
        )
    if report.missing:
        lines.append(f"Gold products not in the current data (skipped): {len(report.missing)}.")
    lines += [
        "",
        "## Most common confusions",
        "",
        f"| {truth} | Model said | Count |",
        "| --- | --- | ---: |",
        *[f"| {names.get(t, t)} | {names.get(p, p)} | {c} |" for t, p, c in o.confusions],
        "",
        "## By category",
        "",
        f"| Category | {'Labelled' if gold else 'Sampled'} products | Recall | Precision |",
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
    parser.add_argument(
        "--labels",
        choices=list(LABELS),
        default="gold",
        help="gold: your hand labels; silver: Claude Opus 5.5's labels (reported as such)",
    )
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
        truth = load_gold(LABELS[args.labels][0])
        name_only, label_suffix = args.name_only, ("name-only" if args.name_only else "full")
        if args.labels != "gold":
            label_suffix += f"-{args.labels}"

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
        against="tags" if args.tagged_sample else "gold",
        labels="" if args.tagged_sample else LABELS[args.labels][1],
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
            "Products Open Food Facts' tags place": score(
                [(truth[c], predicted[c]) for c in tagged]
            ),
            "Products they do not (what the fill is for)": score(
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
