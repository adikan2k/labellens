"""Fill missing categories with the model, from each product's name, brand and ingredients.

    uv run python -m pipeline.enrich.categories --limit 1000             # estimate only
    uv run python -m pipeline.enrich.categories --limit 1000000 --yes    # send

Products that Open Food Facts' tags already place in a category are left alone. The rest
(int_category_inputs where tag_category is null) are sent 50 to a request through the Batch
API, most-scanned first, and answered with one of the 26 leaf categories in dim_categories.
"Other or unclear" is the answer when the name does not say what the product is.

Results go to pipeline/enrich/outputs/categories.parquet (committed), one row per product.
dbt reads it into dim_products with category_source 'model'. Run dbt build first, so the
inputs are current, and again after, so the results reach the marts.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from pipeline.enrich import core

ROOT = Path(__file__).resolve().parents[2]
CATEGORIES_CSV = ROOT / "pipeline" / "dbt" / "seeds" / "dim_categories.csv"
DUCKDB_PATH = ROOT / "data" / "labellens.duckdb"
OUTPUT = core.OUTPUTS / "categories.parquet"

# What each leaf covers, written to match how category_map files Open Food Facts' tags, so
# the model and the tags draw the same lines.
GUIDE: dict[str, str] = {
    "sodas": "carbonated soft drinks, colas, sparkling flavored drinks, energy drinks",
    "juices": "fruit and vegetable juices, nectars, juice drinks, coconut water, smoothies",
    "water-coffee-tea": "still and sparkling water, coffee, tea, iced tea, kombucha, cocoa mixes",
    "salty-snacks": "chips, crisps, popcorn, pretzels, crackers, pork rinds, savory snack mixes",
    "cookies-cakes": "cookies, biscuits, cakes, pastries, donuts, muffins, pies, brownies",
    "candy-chocolate": "candy, chocolate bars, gummies, mints, chewing gum, marshmallows",
    "frozen-desserts": "ice cream, sorbet, frozen yogurt, popsicles, frozen novelties",
    "nuts-bars": "nuts, seeds, trail mix, granola bars, cereal bars, protein bars",
    "milk": "milk, plant milks (oat, almond, soy), cream, half and half, creamers, milk drinks",
    "cheese": "all cheeses, cheese slices, shredded cheese, cream cheese, plant-based cheese",
    "yogurt": "yogurt, kefir, puddings and other dairy desserts",
    "meat": "fresh or frozen beef, pork, chicken, turkey, lamb, burgers, ground meat",
    "deli-meats": "ham, bacon, sausages, hot dogs, salami, sliced deli meat, jerky",
    "seafood": "fish and shellfish, fresh, frozen or canned (canned tuna and salmon count here)",
    "eggs-alternatives": "eggs, egg substitutes, tofu, tempeh, plant-based meat",
    "bread": "bread, rolls, buns, bagels, tortillas, wraps, pita, English muffins",
    "breakfast-cereals": "cold cereal, granola, muesli, oatmeal and other hot cereals",
    "pasta-rice": "dry pasta, noodles, rice, quinoa and other grains, dry beans, lentils",
    "sauces-condiments": "sauces, dressings, dips, hummus, salsa, ketchup, mustard, vinegar, "
    "pickles, olives, gravy and seasoning sauces",
    "spreads": "jams, jellies, honey, peanut butter and other nut butters, chocolate spreads",
    "cooking-baking": "oils, butter, margarine, sugar, syrups, flour, baking mixes, spices, "
    "herbs, salt, seasoning blends, extracts",
    "canned-soups": "soups, broths, and canned or jarred vegetables, beans, fruit and meals "
    "(but canned fish is seafood)",
    "fruit-veg": "fresh, frozen or dried fruits and vegetables, applesauce, fruit cups",
    "prepared-meals": "frozen and ready meals, pizza, sandwiches, burritos, mac and cheese, "
    "meal kits, breaded and fried foods, prepared salads",
    "supplements": "vitamins, dietary supplements, protein powders, meal-replacement powders",
    "other": "alcoholic drinks, baby food, non-food items, and anything the name does not "
    "identify clearly enough to place",
}


def leaf_categories(path: Path = CATEGORIES_CSV) -> dict[str, str]:
    """category_id -> name for every category that is no other category's parent."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    parents = {r["parent_id"] for r in rows if r["parent_id"]}
    return {r["category_id"]: r["name"] for r in rows if r["category_id"] not in parents}


class Answer(BaseModel):
    category: str

    @field_validator("category")
    @classmethod
    def known(cls, value: str) -> str:
        if value not in leaf_categories():
            raise ValueError(f"not a category: {value}")
        return value


class CategoryTask:
    name = "categories"
    prompt_version = "categories-v1"
    group_size = 50
    max_tokens = 2048
    output_tokens_per_item = 14  # {"id":12,"category":"breakfast-cereals"}, measured

    def __init__(self) -> None:
        self.leaves = leaf_categories()
        missing = set(self.leaves) ^ set(GUIDE)
        if missing:
            raise ValueError(f"GUIDE and dim_categories disagree on: {sorted(missing)}")

    def system(self) -> str:
        lines = "\n".join(f"- {cid} ({name}): {GUIDE[cid]}" for cid, name in self.leaves.items())
        return (
            "You file packaged food products sold in the United States into a fixed list of "
            "categories, using only the product's name, its brand, and the start of its "
            "ingredient list when given.\n\n"
            f"Categories:\n{lines}\n\n"
            "Rules:\n"
            "- Choose the single category a grocery shopper would look in for this product.\n"
            "- Judge by what the product is, not by one ingredient: a chocolate chip cookie "
            "is cookies-cakes, a cheese pizza is prepared-meals.\n"
            "- Names may be in another language or abbreviated; use them if they are clear.\n"
            "- If the name and ingredients do not tell you what the product is, answer "
            "'other'. Do not guess.\n"
            "- Answer every product, by its number, with a category id from the list."
        )

    def user_message(self, payloads: Sequence[dict[str, Any]]) -> str:
        def line(n: int, p: dict[str, Any]) -> str:
            parts = [f"name: {p['name']}"]
            if p.get("brand"):
                parts.append(f"brand: {p['brand']}")
            if p.get("ingredients"):
                parts.append(f"ingredients: {p['ingredients']}")
            return f"{n}. " + " | ".join(parts)

        return "\n".join(line(n, p) for n, p in enumerate(payloads, start=1))

    def item_schema(self) -> dict[str, Any]:
        return {"category": {"type": "string", "enum": list(self.leaves)}}

    def parse_item(self, payload: dict[str, Any], answer: dict[str, Any]) -> str:
        try:
            return Answer.model_validate({"category": answer.get("category")}).category
        except ValueError as error:
            raise core.InvalidOutput(str(error)) from error


def payload(name: str, brand: str | None, ingredients: str | None) -> dict[str, Any]:
    """The exact input the model sees; fields that are empty are left out of the key too."""
    out: dict[str, Any] = {"name": " ".join(name.split())}
    if brand and brand.strip():
        out["brand"] = " ".join(brand.split())
    if ingredients and ingredients.strip():
        out["ingredients"] = " ".join(ingredients.split())
    return out


def load_items(
    duckdb_path: Path = DUCKDB_PATH,
    *,
    codes: Sequence[str] | None = None,
    untagged_only: bool = True,
    name_only: bool = False,
) -> list[core.Item]:
    """Items from int_category_inputs, most-scanned first (the order --limit takes)."""
    import duckdb

    where = ["true"]
    params: list[Any] = []
    if untagged_only:
        where.append("tag_category is null")
    if codes is not None:
        where.append("code in (select unnest(?))")
        params.append(list(codes))
    with duckdb.connect(str(duckdb_path), read_only=True) as con:
        rows = con.execute(
            f"select code, name, brand, ingredients from int_category_inputs "
            f"where {' and '.join(where)} "
            f"order by scans desc, completeness desc nulls last, code",
            params,
        ).fetchall()
    return [
        core.Item(ref=code, payload=payload(name, brand, None if name_only else ingredients))
        for code, name, brand, ingredients in rows
    ]


def client_factory() -> Any:
    from api.app.config import get_settings

    key = get_settings().anthropic_api_key
    if key is None:
        raise SystemExit("ANTHROPIC_API_KEY is not set (.env). Nothing was sent.")
    import anthropic

    return anthropic.Anthropic(api_key=key.get_secret_value())


def main(argv: list[str] | None = None) -> int:
    from api.app.config import get_settings, price_per_mtok

    parser = argparse.ArgumentParser(description="Fill missing categories with the model.")
    parser.add_argument("--limit", type=int, required=True, help="most products to send")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--duckdb", type=Path, default=DUCKDB_PATH)
    parser.add_argument("--direct", action="store_true", help="Messages API instead of Batch")
    args = parser.parse_args(argv)

    settings = get_settings()
    model = settings.model_default
    items = load_items(args.duckdb)
    print(f"{len(items):,} named products have no category from Open Food Facts' tags.")
    core.run(
        CategoryTask(),
        items,
        client_factory=client_factory,
        settings=core.CallSettings(model=model, thinking_off=True),
        store=core.OutputStore(OUTPUT),
        prices=price_per_mtok(model),
        limit=args.limit,
        yes=args.yes,
        batch=not args.direct,
        prune=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
