"""The graph loader on the fixture: the subset, the caps, and what it sends to Neo4j."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import duckdb
import pytest

from pipeline.load import graph as graph_module
from pipeline.tests.support import Build


class _Result:
    def consume(self) -> None:
        return None


class FakeSession:
    """Records every query and its rows; no database."""

    def __init__(self) -> None:
        self.queries: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def run(self, query: str, **params: Any) -> _Result:
        self.queries.append((query, params))
        return _Result()

    def execute_write(self, work: Any) -> None:
        work(self)


class FakeDriver:
    def __init__(self) -> None:
        self.session_ = FakeSession()

    def session(self) -> FakeSession:
        return self.session_


@pytest.fixture(scope="module")
def con(dbt_fixture: Build) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(str(dbt_fixture.db), read_only=True)
    yield connection
    connection.close()


def test_the_subset_is_graded_categorised_and_in_rank_order(
    con: duckdb.DuckDBPyConnection,
) -> None:
    built = graph_module.build(con)
    products = built.nodes["Product"]
    assert products, "the fixture should put some products in the graph"
    assert all(p["grade"] in "abcde" and p["category"] not in (None, "other") for p in products)
    ranks = [p["rank"] for p in products]
    assert ranks == sorted(ranks)
    assert len(built.edges["IN"]) == len(products)  # every product has exactly one category
    expected = con.execute("select sum(relationships) from int_graph_products").fetchone()
    child_of = len(built.edges["CHILD_OF"])
    assert expected and built.relationship_count == expected[0] + child_of


def test_every_edge_points_at_a_node(con: duckdb.DuckDBPyConnection) -> None:
    built = graph_module.build(con)
    ids = {
        label: {n[graph_module.KEYS[label]] for n in rows} for label, rows in built.nodes.items()
    }
    for kind, rows in built.edges.items():
        src, _, dst, _ = graph_module.EDGE_ENDS[kind]
        assert all(r["source"] in ids[src] and r["target"] in ids[dst] for r in rows), kind


def test_caps_are_enforced_before_any_connection(con: duckdb.DuckDBPyConnection) -> None:
    built = graph_module.build(con)
    graph_module.check(built)  # the fixture fits
    with pytest.raises(SystemExit, match="Not loading"):
        graph_module.check(built, max_rels=built.relationship_count - 1)
    with pytest.raises(SystemExit, match="Not loading"):
        graph_module.check(built, max_nodes=built.node_count - 1)


def test_the_subset_stops_at_the_relationship_cap(dbt_fixture: Build, tmp_path: Any) -> None:
    from pipeline.tests.support import FIXTURE_VARS, run_dbt

    run = run_dbt("build", tmp_path, {**FIXTURE_VARS, "graph_max_relationships": 200})
    assert run.returncode == 0, run.output[-2000:]
    with duckdb.connect(str(tmp_path / "fixture.duckdb"), read_only=True) as small:
        total = small.execute("select coalesce(sum(relationships), 0) from int_graph_products")
        row = total.fetchone()
    assert row is not None and 0 < row[0] <= 200


def test_write_clears_constrains_then_creates_nodes_before_edges(
    con: duckdb.DuckDBPyConnection,
) -> None:
    built = graph_module.build(con)
    driver = FakeDriver()
    graph_module.write(driver, built, log=lambda _: None)
    queries = driver.session_.queries

    assert "DETACH DELETE" in queries[0][0]
    constraints = [q for q, _ in queries if q.startswith("CREATE CONSTRAINT")]
    assert len(constraints) == len(graph_module.KEYS)
    creates = [(q, p) for q, p in queries if q.startswith("UNWIND")]
    first_edge = next(i for i, (q, _) in enumerate(creates) if "MATCH" in q)
    assert all("MATCH" not in q for q, _ in creates[:first_edge])  # nodes before edges
    sent = sum(len(p["rows"]) for _, p in creates)
    assert sent == built.node_count + built.relationship_count
    assert all(len(p["rows"]) <= graph_module.BATCH for _, p in creates)
    assert "CREATE (:Meta" in queries[-1][0]
