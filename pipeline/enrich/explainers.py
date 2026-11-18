"""Plain-English explainers for additives and common ingredients, written once each.

    uv run python -m pipeline.enrich.explainers --limit 2000             # estimate only
    uv run python -m pipeline.enrich.explainers --limit 2000 --yes       # send

One explainer per additive (all of dim_additives) and per common ingredient (the 500
English ingredient ids used by the most US products, excluding additives, which reuse the
additive's explainer). Not per product.

The rules come from SPEC section 7: neutral and factual, saying what the substance is and
why it is used. No health claims, no advice. For additives, Open Food Facts' taxonomy facts
(name, E-number, functional classes, vegan and vegetarian status) are in the prompt and the
model is told to prefer them. Every text is checked against those rules; one that fails is
retried once, then left null. The UI marks explainers as written by AI.

Results go to pipeline/enrich/outputs/{additive,ingredient}_explainers.jsonl, committed and
readable in review.
"""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator

from pipeline.enrich import core
from pipeline.enrich.categories import DUCKDB_PATH, client_factory

COMMON_INGREDIENTS = 500
MIN_CHARS, MAX_CHARS = 40, 320

# Words that make a health, safety or advice claim, which explainers must not make.
CLAIMS = re.compile(
    r"\b(safe|safely|safety|unsafe|harmful|harmless|healthy|unhealthy|healthier|nutritious|"
    r"beneficial|benefits?|toxic|dangerous|risks?|cancer|carcinogen\w*|disease|cure|prevents?|"
    r"linked to|good for|bad for|should|avoid|recommend\w*)\b",
    re.IGNORECASE,
)
SECOND_PERSON = re.compile(r"\b(you|your|yours)\b", re.IGNORECASE)

RULES = (
    "Rules for every explainer:\n"
    f"- One or two plain sentences, {MIN_CHARS} to {MAX_CHARS - 20} characters.\n"
    "- Say what the substance is (what it is made from, or what kind of substance it is) and "
    "what it does in food.\n"
    "- Neutral and factual. No health, safety or nutrition claims, no judgement of whether "
    "it is good or bad, no advice, no mention of regulators or studies.\n"
    "- Do not address the reader.\n"
    "- Do not start with the substance's name; start with what it is."
)


class Explainer(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def follows_the_rules(cls, value: str) -> str:
        text = " ".join(value.split())
        if not MIN_CHARS <= len(text) <= MAX_CHARS:
            raise ValueError(f"{len(text)} characters")
        if claim := CLAIMS.search(text):
            raise ValueError(f"makes a claim: {claim.group(0)!r}")
        if SECOND_PERSON.search(text):
            raise ValueError("addresses the reader")
        return text


class _ExplainerTask:
    group_size = 10
    max_tokens = 2048
    output_tokens_per_item = 80

    def item_schema(self) -> dict[str, Any]:
        return {"text": {"type": "string"}}

    def parse_item(self, payload: dict[str, Any], answer: dict[str, Any]) -> str:
        try:
            return Explainer.model_validate({"text": answer.get("text")}).text
        except ValueError as error:
            raise core.InvalidOutput(str(error)) from error


class AdditiveTask(_ExplainerTask):
    name = "additive_explainers"
    prompt_version = "additives-v1"

    def system(self) -> str:
        return (
            "You write short, neutral explainers for food additives listed on US packaged "
            "food labels, for shoppers who want to know what an additive is.\n\n"
            "Each additive comes with facts from Open Food Facts' additives taxonomy. Prefer "
            "those facts; where they differ from what you know, follow them. If the taxonomy "
            "says it is not vegan or not vegetarian, it comes from an animal source; say so "
            "if you know which.\n\n" + RULES
        )

    def user_message(self, payloads: Sequence[dict[str, Any]]) -> str:
        def line(n: int, p: dict[str, Any]) -> str:
            facts = [f"{k}: {v}" for k, v in p.items() if v]
            return f"{n}. " + " | ".join(facts)

        return "\n".join(line(n, p) for n, p in enumerate(payloads, start=1))


class IngredientTask(_ExplainerTask):
    name = "ingredient_explainers"
    prompt_version = "ingredients-v1"

    def system(self) -> str:
        return (
            "You write short, neutral explainers for ingredients listed on US packaged food "
            "labels, for shoppers who want to know what an ingredient is and why it is in the "
            "product. Each ingredient comes with its Open Food Facts taxonomy id and the "
            "spelling most labels use.\n\n" + RULES
        )

    def user_message(self, payloads: Sequence[dict[str, Any]]) -> str:
        return "\n".join(
            f"{n}. {p['name']} (taxonomy id {p['id']})" for n, p in enumerate(payloads, start=1)
        )


def additive_items(duckdb_path: Path = DUCKDB_PATH) -> list[core.Item]:
    import duckdb

    with duckdb.connect(str(duckdb_path), read_only=True) as con:
        rows = con.execute(
            "select additive_id, e_number, name, function, vegan, vegetarian "
            "from dim_additives order by product_count desc, additive_id"
        ).fetchall()
    return [
        core.Item(
            ref=additive_id,
            payload={
                "e_number": e_number,
                "name": name,
                "functions": function,
                "vegan": vegan,
                "vegetarian": vegetarian,
            },
        )
        for additive_id, e_number, name, function, vegan, vegetarian in rows
    ]


def ingredient_items(
    duckdb_path: Path = DUCKDB_PATH, top: int = COMMON_INGREDIENTS
) -> list[core.Item]:
    """The `top` English ingredients by product count that are not additives."""
    import duckdb

    with duckdb.connect(str(duckdb_path), read_only=True) as con:
        rows = con.execute(
            """
            select ingredient_id, name from dim_ingredients
            where ingredient_id like 'en:%'
              and not regexp_matches(ingredient_id, '^en:e\\d')
              and ingredient_id not in (select additive_id from dim_additives)
            order by product_count desc, ingredient_id
            limit ?
            """,
            [top],
        ).fetchall()
    return [core.Item(ref=iid, payload={"id": iid, "name": name}) for iid, name in rows]


def main(argv: list[str] | None = None) -> int:
    from api.app.config import get_settings, price_per_mtok

    parser = argparse.ArgumentParser(description="Write additive and ingredient explainers.")
    parser.add_argument("--limit", type=int, required=True, help="most explainers per kind")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--only", choices=["additives", "ingredients"])
    parser.add_argument("--duckdb", type=Path, default=DUCKDB_PATH)
    parser.add_argument("--direct", action="store_true", help="Messages API instead of Batch")
    args = parser.parse_args(argv)

    settings = get_settings()
    model = settings.model_default
    jobs = [
        ("additives", AdditiveTask(), additive_items, "additive_explainers.jsonl"),
        ("ingredients", IngredientTask(), ingredient_items, "ingredient_explainers.jsonl"),
    ]
    for kind, task, load, filename in jobs:
        if args.only and args.only != kind:
            continue
        items = load(args.duckdb)
        print(f"\n{kind}: {len(items):,}")
        core.run(
            task,
            items,
            client_factory=client_factory,
            settings=core.CallSettings(model=model, thinking_off=True),
            store=core.OutputStore(core.OUTPUTS / filename),
            prices=price_per_mtok(model),
            limit=args.limit,
            yes=args.yes,
            batch=not args.direct,
            prune=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
