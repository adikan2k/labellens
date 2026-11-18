"""Explainer tasks: the SPEC's rules are enforced, and inputs come from the marts."""

from __future__ import annotations

import re

import pytest

from pipeline.enrich import core, explainers
from pipeline.tests.support import Build

GOOD = (
    "An acid found in citrus fruit, made by fermentation, that adds a sour taste and keeps colour."
)


def parse(text: object) -> str:
    return explainers.AdditiveTask().parse_item({}, {"id": 1, "text": text})


def test_a_neutral_factual_explainer_passes_and_is_tidied() -> None:
    assert parse(GOOD) == GOOD
    assert parse("  " + GOOD.replace(" ", "  ") + "\n") == GOOD


@pytest.mark.parametrize(
    "text",
    [
        "An acid from citrus fruit that is generally recognized as safe and adds a sour taste.",
        "A sweetener made from corn that some studies have linked to weight gain in adults.",
        "A colouring from beetroot that is healthier than synthetic dyes used in candy.",
        "A thickener from seaweed. People with sensitive stomachs should avoid it entirely.",
        "A preservative that keeps your bread fresh for longer by stopping mould growth.",
        "Too short.",
        "x" * 400,
        None,
    ],
)
def test_claims_advice_second_person_and_bad_lengths_are_rejected(text: object) -> None:
    with pytest.raises(core.InvalidOutput):
        parse(text)


def test_prompts_carry_the_rules_and_the_taxonomy_facts() -> None:
    additive = explainers.AdditiveTask()
    assert "No health, safety or nutrition claims" in additive.system()
    assert "Prefer those facts" in additive.system()
    line = additive.user_message(
        [
            {
                "e_number": "E330",
                "name": "Citric acid",
                "functions": "Acidity regulator",
                "vegan": "yes",
                "vegetarian": None,
            }
        ]
    )
    assert (
        line == "1. e_number: E330 | name: Citric acid | functions: Acidity regulator | vegan: yes"
    )
    ingredient = explainers.IngredientTask().user_message([{"id": "en:sugar", "name": "Sugar"}])
    assert ingredient == "1. Sugar (taxonomy id en:sugar)"


def test_items_come_from_the_marts(dbt_fixture: Build) -> None:
    import duckdb

    additives = explainers.additive_items(dbt_fixture.db)
    with duckdb.connect(str(dbt_fixture.db), read_only=True) as con:
        count = con.execute("select count(*) from dim_additives").fetchone()
        additive_ids = {
            a for (a,) in con.execute("select additive_id from dim_additives").fetchall()
        }
    assert count and len(additives) == count[0]
    assert {"e_number", "name", "functions", "vegan", "vegetarian"} == set(additives[0].payload)

    ingredients = explainers.ingredient_items(dbt_fixture.db, top=50)
    assert 0 < len(ingredients) <= 50
    for item in ingredients:
        assert item.ref.startswith("en:") and item.ref not in additive_ids
        assert not re.match(r"en:e\d", item.ref)  # E-numbers reuse the additive explainer
