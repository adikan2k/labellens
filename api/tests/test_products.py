"""GET /products/{code} and GET /stats/overview against the fixture in Postgres."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app.config import Settings
from api.app.main import create_app


@pytest.fixture(scope="module")
def client(serving_url: str) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, database_url=serving_url)  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def rich(serving_url: str) -> dict[str, Any]:
    """A product with ingredients, additives and a category."""
    with psycopg.connect(serving_url, autocommit=True) as pg:
        row = (
            pg.cursor(row_factory=dict_row)
            .execute(
                "select * from serving.products where cardinality(ingredient_ids) > 2 "
                "and cardinality(additive_ids) > 1 and category_id is not null "
                "order by rank_pos limit 1"
            )
            .fetchone()
        )
    if row is None:
        pytest.skip("fixture has no product with ingredients, additives and a category")
    return row


def test_product_has_label_nutrition_and_lists_in_order(
    client: TestClient, rich: dict[str, Any]
) -> None:
    response = client.get(f"/products/{rich['code']}")
    assert response.status_code == 200, response.text
    body = response.json()
    product = body["product"]

    assert product["code"] == rich["code"]
    assert product["name"] == rich["name"]
    assert product["category_main"] == rich["category_id"]
    assert product["category_name"]
    assert product["off_url"] == f"https://world.openfoodfacts.org/product/{rich['code']}"
    assert set(product["nutrition"]) == {
        "energy_kcal_100g", "sugars_100g", "salt_100g", "fat_100g", "saturated_fat_100g",
        "fiber_100g", "proteins_100g",
    }  # fmt: skip
    assert [i["ingredient_id"] for i in product["ingredients"]] == rich["ingredient_ids"]
    assert [i["rank"] for i in product["ingredients"]] == list(
        range(1, len(rich["ingredient_ids"]) + 1)
    )
    assert [a["additive_id"] for a in product["additives"]] == rich["additive_ids"]
    for additive in product["additives"]:
        assert set(additive) == {
            "additive_id",
            "e_number",
            "name",
            "function",
            "explainer",
            "flagged",
        }
    assert product["category_source"] in ("off_tags", "model", None)
    assert body["source"]["snapshot_date"] == "2026-11-17"
    assert response.headers["cache-control"] == "public, max-age=3600"


def test_citric_acid_reads_as_a_name_with_its_function(
    client: TestClient, serving_url: str
) -> None:
    with psycopg.connect(serving_url, autocommit=True) as pg:
        row = pg.execute(
            "select code from serving.products where 'en:e330' = any(additive_ids) limit 1"
        ).fetchone()
    if row is None:
        pytest.skip("no fixture product with citric acid")
    additives = client.get(f"/products/{row[0]}").json()["product"]["additives"]
    citric = next(a for a in additives if a["additive_id"] == "en:e330")
    assert (citric["e_number"], citric["name"], citric["function"]) == (
        "E330",
        "Citric acid",
        "Antioxidant, sequestrant",
    )
    # From the fixture's enrichment outputs (pipeline/tests/fixtures/enrich).
    assert citric["explainer"]["ai_generated"] is True
    assert citric["explainer"]["text"].startswith("An acid found in citrus fruit")


def test_a_model_category_says_so(client: TestClient) -> None:
    # The fixture's enrichment outputs file 000287050 (no category tags) as supplements.
    product = client.get("/products/000287050").json()["product"]
    assert (product["category_main"], product["category_source"]) == ("supplements", "model")
    assert product["category_name"] == "Supplements and protein powders"


def test_ingredients_carry_their_explainer_or_null(client: TestClient, serving_url: str) -> None:
    with psycopg.connect(serving_url, autocommit=True) as pg:
        row = pg.execute(
            "select code from serving.products where 'en:salt' = any(ingredient_ids) limit 1"
        ).fetchone()
    if row is None:
        pytest.skip("no fixture product with salt")
    ingredients = client.get(f"/products/{row[0]}").json()["product"]["ingredients"]
    salt = next(i for i in ingredients if i["ingredient_id"] == "en:salt")
    assert salt["explainer"] == {
        "text": "Sodium chloride, a mineral mined or evaporated from seawater, used for taste "
        "and to preserve food.",
        "ai_generated": True,
    }
    others = [i for i in ingredients if i["ingredient_id"] not in ("en:salt", "en:e330", "en:e322")]
    assert all(i["explainer"] is None for i in others)


def test_unknown_barcode_is_a_404_with_source(client: TestClient) -> None:
    response = client.get("/products/0000000000000")
    assert response.status_code == 404
    body = response.json()
    assert body["detail"] == "No product with barcode 0000000000000 in this snapshot."
    assert body["source"]["licence"] == "ODbL-1.0"


def test_overlong_barcode_is_rejected(client: TestClient) -> None:
    assert client.get("/products/" + "1" * 33).status_code == 422


def test_stats_overview_is_the_loaded_document(client: TestClient, serving_url: str) -> None:
    response = client.get("/stats/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    with psycopg.connect(serving_url, autocommit=True) as pg:
        doc = pg.execute("select doc from serving.stats").fetchone()
    assert doc
    assert {k: v for k, v in body.items() if k != "source"} == doc[0]
    assert body["source"]["snapshot_date"] == "2026-11-17"
    assert response.headers["cache-control"] == "public, max-age=3600"
