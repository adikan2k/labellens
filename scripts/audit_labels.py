"""Blind check of the AI-written category labels: you label 30 of the 200 products yourself.

    uv run python scripts/audit_labels.py           # label the 30 (resumes; u undo, q quit)
    uv run python scripts/audit_labels.py report    # how often you and the AI labels agree

The 200 eval labels (evals/datasets/category_silver_opus.csv) were written by Claude Opus 5.5,
not a person. This draws a fixed 30 of those products and shows them in the same labeller,
without the AI's label, so your choice is not anchored to it. The report then gives the share
of the 30 where you agree with the AI labels, and lists the rest. Your 30 labels are also a
small human-labelled set: `category_accuracy --labels audit` scores the model on them.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import label  # noqa: E402

DATASETS = ROOT / "evals" / "datasets"
SILVER = DATASETS / "category_silver_opus.csv"
AUDIT_SAMPLE = DATASETS / "category_audit_sample.csv"
AUDIT_LABELS = DATASETS / "category_audit_human.csv"
AUDIT_SIZE = 30
AUDIT_SEED = "labellens-audit-v1"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def draw(sample: Path = label.SAMPLE_PATH, out: Path = AUDIT_SAMPLE, size: int = AUDIT_SIZE) -> int:
    """Write a fixed `size` of the 200 sample products, chosen by a hash of the barcode."""
    rows = _read(sample)
    rows.sort(key=lambda r: hashlib.md5(f"{r['code']}:{AUDIT_SEED}".encode()).hexdigest())
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=label.SAMPLE_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows({k: r[k] for k in label.SAMPLE_FIELDS} for r in rows[:size])
    return size


def compare(
    silver: Path = SILVER, human: Path = AUDIT_LABELS
) -> tuple[int, int, list[tuple[str, str, str]]]:
    """(agreements, products checked, [(code, ai label, your label)] where they differ)."""
    ai = {r["code"]: r["category_id"] for r in _read(silver)}
    mine = {r["code"]: r["category_id"] for r in _read(human)}
    differ = [(code, ai[code], cat) for code, cat in mine.items() if ai.get(code) != cat]
    return len(mine) - len(differ), len(mine), differ


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind check of the AI category labels.")
    parser.add_argument("command", nargs="?", choices=["label", "report"], default="label")
    args = parser.parse_args(argv)

    if args.command == "report":
        if not AUDIT_LABELS.exists():
            print("No audit labels yet. Run: uv run python scripts/audit_labels.py")
            return 1
        agree, total, differ = compare()
        names = {c.category_id: c.name for c in label.load_categories(label.CATEGORIES_PATH)}
        products = {r["code"]: r["name"] for r in _read(AUDIT_SAMPLE)}
        print(f"You agree with the AI labels on {agree} of {total} ({agree / total:.0%}).")
        for code, ai, mine in differ:
            product = (products.get(code) or code)[:50]
            print(f"  {product:<50}  AI: {names[ai]:<34}  you: {names[mine]}")
        return 0

    if not AUDIT_SAMPLE.exists():
        draw()
    return label.label(sample_path=AUDIT_SAMPLE, gold_path=AUDIT_LABELS)


if __name__ == "__main__":
    raise SystemExit(main())
