"""GET /additives and GET /additives/{slug} on the test fixture."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row

from api.app.additive_guide import additive_id, slug
from api.app.config import Settings
from api.app.db import DictConnection
from api.app.graph import Graph
from api.app.main import create_app


@pytest.fixture(scope="module")
def client(serving_url: str):
    app = create_app(Settings(_env_file=None, database_url=serving_url))  # pyright: ignore[reportCallIssue]
    app.state.graph = Graph(driver=None)
    with TestClient(app) as c:
        yield c


def test_slugs_drop_en_and_keep_other_ids_whole() -> None:
    assert slug("en:e330") == "e330" and additive_id("e330") == "en:e330"
    assert slug("xx:e386") == "xx:e386" and additive_id("xx:e386") == "xx:e386"


def test_the_list_is_every_used_additive_most_common_first(client: TestClient) -> None:
    response = client.get("/additives")
    assert response.status_code == 200
    body = response.json()
    items = body["additives"]
    assert items and body["source"]["name"] == "Open Food Facts"
    counts = [i["product_count"] for i in items]
    assert counts == sorted(counts, reverse=True) and min(counts) > 0
    assert {"slug", "flagged", "e_number"} <= set(items[0])
    assert response.headers["cache-control"] == "public, max-age=3600"


def test_one_additive_matches_the_products_that_list_it(
    client: TestClient, serving_url: str
) -> None:
    top = client.get("/additives").json()["additives"][0]
    body = client.get(f"/additives/{top['slug']}").json()
    assert body["additive_id"] == top["additive_id"]
    with DictConnection.connect(serving_url, row_factory=dict_row) as pg:
        listed: Any = pg.execute(
            "select count(*) as n from serving.products where %s = any(additive_ids)",
            [top["additive_id"]],
        ).fetchone()
        total: Any = pg.execute("select count(*) as n from serving.products").fetchone()
    assert body["product_count"] == listed["n"]
    assert body["share_of_products"] == pytest.approx(listed["n"] / total["n"], abs=1e-4)
    assert 0 < len(body["examples"]) <= 6
    assert len(body["top_categories"]) <= 5
    for category in body["top_categories"]:
        assert category["name"] and 0 < category["products"] <= body["product_count"]
    products = [c["products"] for c in body["top_categories"]]
    assert products == sorted(products, reverse=True)


def test_an_unknown_additive_is_404(client: TestClient) -> None:
    response = client.get("/additives/e99999")
    assert response.status_code == 404 and "e99999" in response.json()["detail"]
