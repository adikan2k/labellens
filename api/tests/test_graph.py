"""GET /graph/neighborhood: the assembly on plain data, and the route with a fake graph."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.app import graph
from api.app.config import Settings
from api.app.main import create_app

CENTER = {
    "product": {"code": "0016000275287", "name": "Cheerios", "grade": "c"},
    "links": [
        {"type": "HAS_INGREDIENT", "rank": 2, "label": "Ingredient", "key": "en:sugar",
         "name": "Sugar", "grade": None, "e_number": None, "explainer": "Sucrose from cane."},
        {"type": "HAS_INGREDIENT", "rank": 1, "label": "Ingredient", "key": "en:oat",
         "name": "Oats", "grade": None, "e_number": None, "explainer": None},
        {"type": "CONTAINS", "rank": None, "label": "Additive", "key": "en:e307",
         "name": "Tocopherol", "grade": None, "e_number": "E307", "explainer": "Vitamin E."},
        {"type": "IN", "rank": None, "label": "Category", "key": "breakfast-cereals",
         "name": "Breakfast cereals and oats", "grade": None, "e_number": None, "explainer": None},
        {"type": "MADE_BY", "rank": None, "label": "Brand", "key": "general mills",
         "name": "General Mills", "grade": None, "e_number": None, "explainer": None},
    ],
    "parent": {"id": "grains", "name": "Bread, cereals and grains"},
}  # fmt: skip


def hub(label: str, key: str, degree: int, *codes: str) -> dict[str, Any]:
    kind = {"Brand": "MADE_BY", "Category": "IN", "Additive": "CONTAINS"}.get(
        label, "HAS_INGREDIENT"
    )
    others = [{"code": c, "name": f"Product {c}", "grade": "b", "type": kind} for c in codes]
    return {"label": label, "key": key, "degree": degree, "others": others}


def test_depth_one_is_the_product_its_links_and_the_category_parent() -> None:
    out = graph.assemble(CENTER, None)
    assert out["center"] == "Product:0016000275287"
    ids = [n["id"] for n in out["nodes"]]
    assert ids == [
        "Product:0016000275287", "Brand:general mills", "Category:breakfast-cereals",
        "Additive:en:e307", "Ingredient:en:oat", "Ingredient:en:sugar", "Category:grains",
    ]  # fmt: skip
    by_id = {n["id"]: n for n in out["nodes"]}
    assert by_id["Additive:en:e307"]["name"] == "E307 Tocopherol"
    assert by_id["Additive:en:e307"]["detail"] == "Vitamin E."
    assert by_id["Product:0016000275287"]["nutriscore_grade"] == "c"
    assert {
        "from": "Category:breakfast-cereals",
        "to": "Category:grains",
        "type": "CHILD_OF",
    } in out["edges"]
    assert len(out["edges"]) == 6 and out["truncated"] is False


def test_depth_two_adds_products_per_hub_and_marks_truncation() -> None:
    hubs = [
        hub("Ingredient", "en:sugar", 5000, "A1", "A2"),
        hub("Brand", "general mills", 3, "B1", "B2"),
    ]
    out = graph.assemble(CENTER, hubs)
    kinds = [n["kind"] for n in out["nodes"]]
    assert kinds.count("Product") == 5
    assert out["truncated"] is True  # sugar has 5,000 products; two were added
    assert {"from": "Product:B1", "to": "Brand:general mills", "type": "MADE_BY"} in out["edges"]

    small = graph.assemble(CENTER, [hub("Brand", "general mills", 3, "B1", "B2")])
    assert small["truncated"] is False


def test_the_node_cap_holds() -> None:
    hubs = [hub("Ingredient", "en:sugar", 41, *[f"P{i}" for i in range(40)])]
    out = graph.assemble(CENTER, hubs, max_nodes=10)
    assert len(out["nodes"]) == 10 and out["truncated"] is True
    ids = {n["id"] for n in out["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in out["edges"])


def test_without_settings_the_graph_is_unavailable() -> None:
    with pytest.raises(graph.GraphUnavailable):
        graph.Graph.open(None, None, None).neighborhood("1", 1)


class FakeGraph:
    def __init__(self) -> None:
        self.fail = False

    def neighborhood(self, code: str, depth: int) -> dict[str, Any] | None:
        if self.fail:
            raise graph.GraphUnavailable("paused")
        if code != CENTER["product"]["code"]:
            return None
        return graph.assemble(
            CENTER, [hub("Brand", "general mills", 3, "B1")] if depth == 2 else None
        )

    def close(self) -> None:
        return None


@pytest.fixture(scope="module")
def fake() -> FakeGraph:
    return FakeGraph()


@pytest.fixture(scope="module")
def client(serving_url: str, fake: FakeGraph) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, database_url=serving_url)  # pyright: ignore[reportCallIssue]
    app = create_app(settings)
    app.state.graph = fake
    with TestClient(app) as test_client:
        yield test_client


def test_route_returns_the_contract_shape(client: TestClient) -> None:
    response = client.get("/graph/neighborhood", params={"code": "0016000275287", "depth": 2})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"center", "nodes", "edges", "truncated", "source"}
    assert set(body["edges"][0]) == {"from", "to", "type"}
    assert set(body["nodes"][0]) == {"id", "kind", "name", "nutriscore_grade", "detail"}
    assert "Product:B1" in {n["id"] for n in body["nodes"]}
    assert response.headers["cache-control"] == "public, max-age=3600"


def test_route_errors(client: TestClient, fake: FakeGraph) -> None:
    missing = client.get("/graph/neighborhood", params={"code": "123"})
    assert missing.status_code == 404
    assert missing.json()["detail"] == "The graph does not hold a product with barcode 123."
    assert client.get("/graph/neighborhood", params={"code": "1", "depth": 3}).status_code == 422
    fake.fail = True
    try:
        paused = client.get("/graph/neighborhood", params={"code": "0016000275287"})
    finally:
        fake.fail = False
    assert paused.status_code == 503
    assert "graph is waking up" in paused.json()["detail"]


def test_encrypted_addresses_trust_the_mozilla_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    import certifi
    import neo4j

    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        neo4j.GraphDatabase, "driver", lambda uri, **kw: calls.append((uri, kw)) or object()
    )
    graph.make_driver("neo4j+s://abc.databases.neo4j.io", "neo4j", "pw", connection_timeout=8)
    graph.make_driver("bolt://localhost:57687", "neo4j", "pw")
    (secure_uri, secure), (local_uri, local) = calls
    assert secure_uri == "neo4j://abc.databases.neo4j.io"
    assert secure["encrypted"] is True and secure["connection_timeout"] == 8
    assert isinstance(secure["trusted_certificates"], neo4j.TrustCustomCAs)
    assert certifi.where() in secure["trusted_certificates"].certs
    assert local_uri == "bolt://localhost:57687" and "encrypted" not in local
