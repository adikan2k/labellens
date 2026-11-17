"""Terminal labeller for the category gold set.

    uv run python scripts/label.py            # label; resumes where you stopped
    uv run python scripts/label.py sample     # draw the 200-product sample (once)

Shows each sampled product's name, brand and ingredients, takes a category number from
`dim_categories`, and appends it to `evals/datasets/category_gold.csv` straight away.
`u` undoes the last label, `q` quits. Open Food Facts' own category is not shown, so it
cannot anchor your choice.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = ROOT / "evals" / "datasets" / "category_sample.csv"
GOLD_PATH = ROOT / "evals" / "datasets" / "category_gold.csv"
CATEGORIES_PATH = ROOT / "pipeline" / "dbt" / "seeds" / "dim_categories.csv"

SAMPLE_FIELDS = ["code", "name", "brand", "ingredients", "snapshot_date"]
GOLD_FIELDS = ["code", "category_id", "labelled_at"]
WIDTH = 88


@dataclass(frozen=True)
class Category:
    category_id: str
    name: str


@dataclass(frozen=True)
class Product:
    code: str
    name: str
    brand: str
    ingredients: str


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def load_categories(path: Path) -> list[Category]:
    """Leaf categories in file order; a category that is some row's parent is not offered."""
    rows = _read_csv(path)
    parents = {row["parent_id"] for row in rows if row.get("parent_id")}
    return [Category(r["category_id"], r["name"]) for r in rows if r["category_id"] not in parents]


def load_sample(path: Path) -> list[Product]:
    return [Product(r["code"], r["name"], r["brand"], r["ingredients"]) for r in _read_csv(path)]


def load_gold(path: Path) -> list[dict[str, str]]:
    return _read_csv(path) if path.exists() else []


def append_gold(path: Path, code: str, category_id: str) -> None:
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GOLD_FIELDS, lineterminator="\n")
        if new_file:
            writer.writeheader()
        labelled_at = datetime.now(UTC).isoformat(timespec="seconds")
        writer.writerow({"code": code, "category_id": category_id, "labelled_at": labelled_at})
        handle.flush()
        os.fsync(handle.fileno())


def rewrite_gold(path: Path, rows: list[dict[str, str]]) -> None:
    tmp = path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=GOLD_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def _show(product: Product, position: int, total: int, categories: list[Category], out: TextIO):
    def field(label: str, value: str) -> str:
        text = value.strip() or "(none recorded)"
        return textwrap.fill(text, WIDTH, initial_indent=f"{label:<13}", subsequent_indent=" " * 13)

    print("\n" + "=" * WIDTH, file=out)
    print(f"[{position}/{total}]  barcode {product.code}", file=out)
    print(field("Name", product.name), file=out)
    print(field("Brand", product.brand), file=out)
    print(field("Ingredients", product.ingredients), file=out)
    print("-" * WIDTH, file=out)
    half = (len(categories) + 1) // 2
    for i in range(half):
        left = f"{i + 1:>3}  {categories[i].name}"
        right = ""
        if i + half < len(categories):
            right = f"{i + half + 1:>3}  {categories[i + half].name}"
        print(f"{left:<44}{right}", file=out)


def label(
    sample_path: Path = SAMPLE_PATH,
    categories_path: Path = CATEGORIES_PATH,
    gold_path: Path = GOLD_PATH,
    *,
    ask: Callable[[str], str] = input,
    out: TextIO = sys.stdout,
) -> int:
    categories = load_categories(categories_path)
    products = load_sample(sample_path)
    by_code = {p.code: p for p in products}
    valid_ids = {c.category_id for c in categories}

    gold = load_gold(gold_path)
    stray = [r["code"] for r in gold if r["code"] not in by_code]
    if stray:
        print(f"{len(stray)} labelled barcodes are not in the sample: {stray[:5]}", file=out)
        return 1
    unknown = [r["category_id"] for r in gold if r["category_id"] not in valid_ids]
    if unknown:
        print(f"Labels use categories not in the taxonomy: {sorted(set(unknown))}", file=out)
        return 1

    while True:
        done = {r["code"] for r in gold}
        remaining = [p for p in products if p.code not in done]
        if not remaining:
            print(f"\nAll {len(products)} products labelled. Saved to {gold_path}.", file=out)
            return 0

        product = remaining[0]
        _show(product, len(done) + 1, len(products), categories, out)
        try:
            answer = ask("Category number, u to undo, q to quit: ").strip().lower()
        except EOFError:
            answer = "q"

        if answer == "q":
            print(f"\nStopped at {len(done)} of {len(products)}. Run again to resume.", file=out)
            return 0
        if answer == "u":
            if not gold:
                print("Nothing to undo.", file=out)
                continue
            removed = gold.pop()
            rewrite_gold(gold_path, gold)
            print(f"Undid label for {removed['code']}.", file=out)
            continue
        if answer.isdigit() and 1 <= int(answer) <= len(categories):
            category = categories[int(answer) - 1]
            append_gold(gold_path, product.code, category.category_id)
            gold = load_gold(gold_path)
            print(f"Saved: {category.name}", file=out)
            continue
        print(f"Type a number from 1 to {len(categories)}, u or q.", file=out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Label the category gold set.")
    parser.add_argument("command", nargs="?", choices=["label", "sample"], default="label")
    args = parser.parse_args(argv)
    if args.command == "sample":
        print("The sample step is added once docs/data-profile.md exists.", file=sys.stderr)
        return 1
    return label()


if __name__ == "__main__":
    raise SystemExit(main())
