"""The label-reading eval's dataset: US products with both an ingredients photo and a
nutrition photo on Open Food Facts, and what a correct read should find.

    uv run python -m evals.datasets.build_labels               # writes evals/datasets/labels.jsonl
    uv run python -m evals.datasets.build_labels --download    # and fetches the photos

Products come from the built marts (data/labellens.duckdb): a real barcode, a category, an
ingredient list, and energy, fat, sugars, salt and protein all known. They are spread across
categories, two at most per category, most-scanned first. The photos' keys and revisions come
from the newest raw export, which is only read.

Truth is Open Food Facts' own data: per 100 g nutrition from fct_nutrition and the additives
from bridge_product_additives. Contributors enter it, so it has mistakes of its own; the eval
report says how many misses were the truth's fault.

The photos (CC BY-SA, Open Food Facts contributors) are fetched into evals/cache/label_images/,
which git ignores: they are used here, not redistributed.
"""

from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = ROOT / "data" / "labellens.duckdb"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "evals" / "datasets" / "labels.jsonl"
IMAGES = ROOT / "evals" / "cache" / "label_images"
IMAGE_BASE = "https://images.openfoodfacts.org/images/products/"
USER_AGENT = "labellens-eval/1"
SIZE = 30
ENGLISH = 22  # of SIZE: US-style English labels first; the rest test labels in other languages
PER_CATEGORY = 2

NUTRIENTS = (
    "energy_kcal_100g",
    "sugars_100g",
    "salt_100g",
    "fat_100g",
    "saturated_fat_100g",
    "fiber_100g",
    "proteins_100g",
)

CANDIDATES_SQL = f"""
select p.code, p.name, p.brand, p.category_main as category, p.scans,
       {", ".join(f"n.{n}" for n in NUTRIENTS)}
from dim_products p
join fct_nutrition n using (code)
where p.gtin_valid
  and p.category_main is not null and p.category_main <> 'other'
  and p.name is not null
  and n.energy_kcal_100g is not null and n.fat_100g is not null
  and n.sugars_100g is not null and n.salt_100g is not null and n.proteins_100g is not null
  and exists (select 1 from bridge_product_ingredients i where i.code = p.code)
order by p.scans desc, p.code
limit 3000
"""

# The ingredients and nutrition photos: English first, then the product's language, then any.
PHOTOS_SQL = """
with picked as (
    select code, lang,
        coalesce(
            list_filter(images, lambda x: x.key = 'ingredients_en' and x.rev is not null)[1],
            list_filter(images, lambda x: x.key = 'ingredients_' || lang and x.rev is not null)[1],
            list_filter(
                images, lambda x: starts_with(x.key, 'ingredients_') and x.rev is not null
            )[1]
        ) as ingredients,
        coalesce(
            list_filter(images, lambda x: x.key = 'nutrition_en' and x.rev is not null)[1],
            list_filter(images, lambda x: x.key = 'nutrition_' || lang and x.rev is not null)[1],
            list_filter(images, lambda x: starts_with(x.key, 'nutrition_') and x.rev is not null)[1]
        ) as nutrition
    from read_parquet(?)
    where code in (select unnest(?::varchar[]))
)
select code, ingredients.key as ingredients_key, ingredients.rev as ingredients_rev,
       nutrition.key as nutrition_key, nutrition.rev as nutrition_rev
from picked
where ingredients is not null and nutrition is not null
"""


def image_folder(code: str) -> str:
    """Open Food Facts' folder for a barcode (pipeline/dbt/macros/images.sql)."""
    if len(code) <= 8:
        return code
    padded = code.zfill(13) if len(code) < 13 else code
    return f"{padded[:3]}/{padded[3:6]}/{padded[6:9]}/{padded[9:]}"


def image_url(code: str, key: str, rev: int) -> str:
    return f"{IMAGE_BASE}{image_folder(code)}/{key}.{rev}.full.jpg"


def newest_export() -> Path:
    return sorted(RAW.glob("*/food.parquet"))[-1]


def build(con: duckdb.DuckDBPyConnection, parquet: Path, size: int = SIZE) -> list[dict[str, Any]]:
    cur = con.execute(CANDIDATES_SQL)
    columns = [d[0] for d in cur.description]
    candidates = [dict(zip(columns, row, strict=True)) for row in cur.fetchall()]
    codes = [c["code"] for c in candidates]
    photos = {row[0]: row for row in con.execute(PHOTOS_SQL, [str(parquet), codes]).fetchall()}

    def english(code: str) -> bool:
        _, ing_key, _, nut_key, _ = photos[code]
        return ing_key.endswith("_en") and nut_key.endswith("_en")

    picked: list[dict[str, Any]] = []
    per_category: dict[str, int] = {}
    # English labels first, up to ENGLISH of them; then labels in other languages.
    for want_english, quota in ((True, min(ENGLISH, size)), (False, size)):
        for product in candidates:  # most-scanned first
            if len(picked) >= quota:
                break
            code, category = product["code"], product["category"]
            if code not in photos or english(code) != want_english:
                continue
            if per_category.get(category, 0) >= PER_CATEGORY or product in picked:
                continue
            per_category[category] = per_category.get(category, 0) + 1
            picked.append(product)

    additives: dict[str, list[str]] = {}
    for code, additive_id in con.execute(
        "select code, additive_id from bridge_product_additives "
        "where code in (select unnest(?::varchar[])) order by code, additive_id",
        [[p["code"] for p in picked]],
    ).fetchall():
        additives.setdefault(code, []).append(additive_id)

    rows = []
    for n, product in enumerate(picked, start=1):
        _, ing_key, ing_rev, nut_key, nut_rev = photos[product["code"]]
        rows.append(
            {
                "id": f"label-{n:02d}",
                "code": product["code"],
                "name": product["name"],
                "brand": product["brand"],
                "category": product["category"],
                "language": "en" if english(product["code"]) else "other",
                "images": [
                    {"kind": "ingredients", "url": image_url(product["code"], ing_key, ing_rev)},
                    {"kind": "nutrition", "url": image_url(product["code"], nut_key, nut_rev)},
                ],
                "truth": {
                    "nutrition": {k: product[k] for k in NUTRIENTS},
                    "additives": additives.get(product["code"], []),
                },
            }
        )
    return rows


def image_path(row: dict[str, Any], kind: str) -> Path:
    return IMAGES / f"{row['code']}-{kind}.jpg"


def download(rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Fetch the photos not fetched yet. Returns (files fetched, bytes)."""
    IMAGES.mkdir(parents=True, exist_ok=True)
    fetched = total = 0
    for row in rows:
        for image in row["images"]:
            path = image_path(row, image["kind"])
            if path.exists():
                continue
            request = urllib.request.Request(image["url"], headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            path.write_bytes(data)
            fetched += 1
            total += len(data)
            time.sleep(0.3)  # gentle on Open Food Facts' image server
    return fetched, total


def load(path: Path = OUT) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the label-reading eval dataset.")
    parser.add_argument("--size", type=int, default=SIZE)
    parser.add_argument("--download", action="store_true", help="fetch the photos too")
    args = parser.parse_args(argv)

    if OUT.exists() and not args.download:
        print(f"{OUT.relative_to(ROOT)} exists; delete it to rebuild.")
    if not OUT.exists():
        with duckdb.connect(str(DUCKDB_PATH), read_only=True) as con:
            rows = build(con, newest_export(), args.size)
        with open(OUT, "w", encoding="utf-8", newline="\n") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        categories = len({r["category"] for r in rows})
        print(f"Wrote {len(rows)} labels across {categories} categories to {OUT.relative_to(ROOT)}")
    if args.download:
        fetched, total = download(load())
        print(f"Fetched {fetched} photos ({total / 1e6:.1f} MB) into {IMAGES.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
