"""The graph loader and the API's neighbourhood queries against a real Neo4j (docker compose)."""

from __future__ import annotations

from typing import Any

import duckdb
import pytest

from api.app.graph import Graph
from pipeline.load import graph as graph_module
from pipeline.tests.support import Build


@pytest.fixture(scope="module")
def loaded(neo4j_driver: Any, dbt_fixture: Build) -> graph_module.Graph:
    with duckdb.connect(str(dbt_fixture.db), read_only=True) as con:
        built = graph_module.build(con)
    graph_module.write(neo4j_driver, built, log=lambda _: None)
    return built


def _count(driver: Any, query: str) -> int:
    records, _, _ = driver.execute_query(query)
    return records[0][0]


def test_the_database_holds_exactly_the_built_graph(neo4j_driver: Any, loaded: Any) -> None:
    assert _count(neo4j_driver, "MATCH (n) WHERE NOT n:Meta RETURN count(n)") == loaded.node_count
    assert _count(neo4j_driver, "MATCH ()-[r]->() RETURN count(r)") == loaded.relationship_count
    for label, rows in loaded.nodes.items():
        assert _count(neo4j_driver, f"MATCH (n:{label}) RETURN count(n)") == len(rows), label


def test_a_reload_replaces_rather_than_adds(neo4j_driver: Any, loaded: Any) -> None:
    graph_module.write(neo4j_driver, loaded, log=lambda _: None)
    assert _count(neo4j_driver, "MATCH (n) WHERE NOT n:Meta RETURN count(n)") == loaded.node_count
    assert _count(neo4j_driver, "MATCH (m:Meta) RETURN count(m)") == 1


def test_neighbourhood_queries_run_on_neo4j(neo4j_driver: Any, loaded: Any) -> None:
    api_graph = Graph(driver=neo4j_driver)
    # The best-ranked product with the most links makes the richest neighbourhood.
    records, _, _ = neo4j_driver.execute_query(
        "MATCH (p:Product)-[r]->() "
        "RETURN p.code AS code, p.rank AS rank, count(r) AS n ORDER BY n DESC, rank LIMIT 1"
    )
    code = records[0]["code"]

    one = api_graph.neighborhood(code, 1)
    assert one is not None and one["center"] == f"Product:{code}"
    links = _count(neo4j_driver, f"MATCH (:Product {{code: '{code}'}})-[r]->() RETURN count(r)")
    assert sum(1 for e in one["edges"] if e["from"] == one["center"]) == links
    kinds = {n["kind"] for n in one["nodes"]}
    assert {"Product", "Category"} <= kinds

    two = api_graph.neighborhood(code, 2)
    assert two is not None
    assert len(two["nodes"]) >= len(one["nodes"])
    assert len(two["nodes"]) <= 150
    ids = {n["id"] for n in two["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in two["edges"])

    assert api_graph.neighborhood("not-a-barcode", 1) is None
