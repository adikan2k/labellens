"""GET /products/{code}/swaps against the fixture in Postgres, and the reason text."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, LiteralString, cast

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app import swaps
from api.app.config import Settings
from api.app.db import DictConnection
from api.app.main import create_app


@pytest.fixture(scope="module")
def client(serving_url: str) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, database_url=serving_url)  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _rows(serving_url: str, sql: str, params: dict[str, Any] | None = None) -> list[dict]:
    with psycopg.connect(serving_url, autocommit=True) as pg:
        query = cast("LiteralString", sql)  # test-only SQL, no user input
        return pg.cursor(row_factory=dict_row).execute(query, params or {}).fetchall()


@pytest.fixture(scope="module")
def poor(client: TestClient, serving_url: str) -> dict[str, Any]:
    """A product graded C to E with at least one swap (similar by name, so found by trying)."""
    rows = _rows(
        serving_url,
        """select p.* from serving.products p
           where p.nutriscore_grade in ('c', 'd', 'e') and p.category_id <> 'other'
           order by p.nutriscore_grade desc, p.rank_pos""",
    )
    for row in rows:
        if client.get(f"/products/{row['code']}/swaps").json()["swaps"]:
            return row
    pytest.skip("fixture has no product with a swap")


def test_swaps_are_better_unflagged_same_category_and_ranked(
    client: TestClient, serving_url: str, poor: dict[str, Any]
) -> None:
    response = client.get(f"/products/{poor['code']}/swaps", params={"limit": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == poor["code"] and body["source"]["name"] == "Open Food Facts"
    assert response.headers["cache-control"] == "public, max-age=3600"
    found = body["swaps"]
    assert found, "expected at least one swap"

    codes = [s["product"]["code"] for s in found]
    details = {
        r["code"]: r
        for r in _rows(
            serving_url,
            "select code, name, brand, category_id, nutriscore_grade, additive_count, "
            "has_flagged, gtin_valid, cardinality(ingredient_ids) as ingredients, rank_pos "
            "from serving.products "
            "where code = any(%(codes)s)",
            {"codes": codes},
        )
    }
    for swap in found:
        row = details[swap["product"]["code"]]
        assert row["category_id"] == poor["category_id"]
        assert row["nutriscore_grade"] < poor["nutriscore_grade"]
        assert not row["has_flagged"]
        assert row["gtin_valid"], "a swap must have a real barcode (not a menu item)"
        # Without an ingredient list, "no additives" and "none flagged" are unknown, not true.
        assert row["ingredients"] > 0, "a swap must have an ingredient list"
        assert row["code"] != poor["code"]
        assert swap["additive_count"] == row["additive_count"]
        assert swap["reason"].endswith("none flagged by Open Food Facts")
        shared = set(swaps.name_words(row["name"] + " " + (row["brand"] or "")))
        assert shared & set(swaps.name_words(poor["name"])), "a swap must share a name word"
    # Tiers in order (head word and another word, head word only, any other word), and the
    # SPEC ranking (grade, fewest additives, search rank) within each tier.
    mine = swaps.name_words(poor["name"])
    head, others = mine[-1], set(mine[:-1]) - {mine[-1]}

    def tier(code: str) -> int:
        words = set(swaps.name_words(details[code]["name"] + " " + (details[code]["brand"] or "")))
        if head in words and words & others:
            return 0
        return 1 if head in words else 2

    keys = [
        (
            tier(c),
            details[c]["nutriscore_grade"],
            details[c]["additive_count"],
            details[c]["rank_pos"],
        )
        for c in codes
    ]
    assert keys == sorted(keys)
    names = [(details[c]["name"].casefold(), (details[c]["brand"] or "").casefold()) for c in codes]
    assert len(names) == len(set(names)), "the same name and brand appears twice"


def test_a_product_without_an_ingredient_list_is_not_a_swap(serving_url: str) -> None:
    """No ingredient list means its additives are unknown, so "no additives" would be false.

    Open Food Facts had Doritos Spicy Nacho, no ingredients entered, offered as a swap for
    Nacho Cheese Doritos with "no additives instead of 8". The rows here are made up and
    rolled back.
    """
    made_up = [
        # code, name, grade, ingredient ids, additive count
        ("0000000000017", "Zorblax Crunch Chips", "d", ["en:corn"], 3),
        ("0000000000024", "Zorblax Spicy Chips", "b", [], 0),  # no ingredients entered
        ("0000000000031", "Zorblax Lime Chips", "c", ["en:corn", "en:salt"], 1),
    ]
    with DictConnection.connect(serving_url, row_factory=dict_row) as pg:
        # One real row as a template for the columns this test does not care about.
        pg.execute(
            "create temp table made_up as "
            "select * from serving.products where gtin_valid order by rank_pos limit 1"
        )
        for code, name, grade, ingredients, additives in made_up:
            pg.execute(
                """update made_up set code = %(code)s, name = %(name)s, brand = null,
                     category_id = 'salty-snacks', nutriscore_grade = %(grade)s,
                     ingredient_ids = %(ingredients)s, additive_ids = '{}',
                     additive_count = %(additives)s, has_flagged = false""",
                {
                    "code": code,
                    "name": name,
                    "grade": grade,
                    "ingredients": ingredients,
                    "additives": additives,
                },
            )
            pg.execute("insert into serving.products select * from made_up")
        found = swaps.find_swaps(pg, "0000000000017", limit=5)
        pg.rollback()

    assert found is not None
    codes = [s["product"]["code"] for s in found]
    assert "0000000000024" not in codes, "offered a swap whose additives are unknown"
    assert codes[0] == "0000000000031"
    assert found[0]["reason"].startswith("Nutri-Score C instead of D · 1 additive instead of 3")


def test_limit_caps_the_list(client: TestClient, poor: dict[str, Any]) -> None:
    assert (
        len(client.get(f"/products/{poor['code']}/swaps", params={"limit": 1}).json()["swaps"]) <= 1
    )
    assert client.get(f"/products/{poor['code']}/swaps", params={"limit": 21}).status_code == 422


def test_grade_a_ungraded_and_other_get_no_swaps(client: TestClient, serving_url: str) -> None:
    for where in (
        "nutriscore_grade = 'a'",
        "nutriscore_grade is null",
        "category_id = 'other' or category_id is null",
    ):
        rows = _rows(serving_url, f"select code from serving.products where {where} limit 1")
        if rows:
            assert client.get(f"/products/{rows[0]['code']}/swaps").json()["swaps"] == [], where


def test_unknown_barcode_is_a_404(client: TestClient) -> None:
    response = client.get("/products/0000000000000/swaps")
    assert response.status_code == 404
    assert response.json()["detail"] == "No product with barcode 0000000000000 in this snapshot."


def test_reason_is_built_from_the_data() -> None:
    mine = {"nutriscore_grade": "d", "additive_count": 4}
    assert (
        swaps.reason(mine, {"nutriscore_grade": "a", "additive_count": 1})
        == "Nutri-Score A instead of D · 1 additive instead of 4 · none flagged by Open Food Facts"
    )
    assert swaps.reason(mine, {"nutriscore_grade": "b", "additive_count": 0}).startswith(
        "Nutri-Score B instead of D · no additives instead of 4"
    )
    assert "4 additives, the same" in swaps.reason(
        mine, {"nutriscore_grade": "c", "additive_count": 4}
    )


def test_name_words_drop_generic_words_and_keep_the_head_last() -> None:
    assert swaps.name_words("Classic Mayo") == ["mayo"]
    assert swaps.name_words("Organic Raw & Unfiltered Honey") == ["raw", "unfiltered", "honey"]
    assert swaps.name_words("Potato Chips, Sea Salt & Vinegar") == ["potato", "chips"]
    assert swaps.name_words("Original") == []
