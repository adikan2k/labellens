"""Load the food graph into Neo4j (AuraDB Free) from the DuckDB marts.

    uv run python -m pipeline.load.graph --dry-run    # counts only, no connection
    uv run python -m pipeline.load.graph              # replace the graph (NEO4J_* from .env)
    uv run python -m pipeline.load.graph --ping       # one read, to keep AuraDB Free awake

Nodes: Product, Brand, Category, Additive, Ingredient (and one Meta node).
Relationships: (:Product)-[:MADE_BY]->(:Brand), -[:IN]->(:Category), -[:CONTAINS]->(:Additive),
-[:HAS_INGREDIENT {rank}]->(:Ingredient), and (:Category)-[:CHILD_OF]->(:Category).

The products are int_graph_products: graded, named products with a real category, in search
rank order, up to the relationship cap. The node and relationship counts are printed and
checked against the caps (180,000 and 360,000) and AuraDB Free's limits (200,000 and 400,000)
before anything is written.

A load replaces the whole graph: everything is deleted in batches, then recreated. AuraDB
Free holds one database and no room for a second copy, so for about a minute the graph is
empty; the API reports that as "the graph is reloading".
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # DuckDB is in the pipeline group; --ping runs without it (keep-alive)
    import duckdb

ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = ROOT / "data" / "labellens.duckdb"
MAX_NODES, MAX_RELATIONSHIPS = 180_000, 360_000  # SPEC section 5
AURA_FREE_NODES, AURA_FREE_RELATIONSHIPS = 200_000, 400_000
BATCH = 5_000

Log = Callable[[str], None]

PRODUCTS_SQL = """
select p.code, p.name, p.category_main as category, p.nutriscore_grade as grade,
       p.nova_group as nova, g.rank_pos as rank,
       lower(trim(p.brand)) as brand
from int_graph_products g join dim_products p using (code)
order by g.rank_pos
"""

NODE_QUERIES: dict[str, str] = {
    "Brand": """
        select lower(trim(p.brand)) as id, mode(trim(p.brand)) as name
        from int_graph_products g join dim_products p using (code)
        where p.brand is not null group by 1 order by 1
    """,
    "Category": "select category_id as id, name from dim_categories order by 1",
    "Additive": """
        select a.additive_id as id, a.e_number, a.name, a.function, a.explainer, a.flagged
        from dim_additives a
        where a.additive_id in (select b.additive_id from bridge_product_additives b
                                join int_graph_products g using (code))
        order by 1
    """,
    "Ingredient": """
        select i.ingredient_id as id, i.name, i.explainer
        from dim_ingredients i
        where i.ingredient_id in (select b.ingredient_id from bridge_product_ingredients b
                                  join int_graph_products g using (code))
        order by 1
    """,
}

EDGE_QUERIES: dict[str, str] = {
    "MADE_BY": """
        select p.code as source, lower(trim(p.brand)) as target
        from int_graph_products g join dim_products p using (code)
        where p.brand is not null order by 1
    """,
    "IN": """
        select p.code as source, p.category_main as target
        from int_graph_products g join dim_products p using (code) order by 1
    """,
    "CONTAINS": """
        select b.code as source, b.additive_id as target
        from bridge_product_additives b join int_graph_products g using (code) order by 1, 2
    """,
    "HAS_INGREDIENT": """
        select b.code as source, b.ingredient_id as target, b.rank
        from bridge_product_ingredients b join int_graph_products g using (code) order by 1, 3
    """,
    "CHILD_OF": """
        select category_id as source, parent_id as target from dim_categories
        where parent_id is not null order by 1
    """,
}

# (source label, source key, target label, target key) for each relationship type.
EDGE_ENDS: dict[str, tuple[str, str, str, str]] = {
    "MADE_BY": ("Product", "code", "Brand", "id"),
    "IN": ("Product", "code", "Category", "id"),
    "CONTAINS": ("Product", "code", "Additive", "id"),
    "HAS_INGREDIENT": ("Product", "code", "Ingredient", "id"),
    "CHILD_OF": ("Category", "id", "Category", "id"),
}
KEYS = {"Product": "code", "Brand": "id", "Category": "id", "Additive": "id", "Ingredient": "id"}


@dataclass
class Graph:
    nodes: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    edges: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    snapshot_date: str = ""

    @property
    def node_count(self) -> int:
        return sum(len(rows) for rows in self.nodes.values())

    @property
    def relationship_count(self) -> int:
        return sum(len(rows) for rows in self.edges.values())


def _rows(con: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    cursor = con.execute(query)
    names = [d[0] for d in cursor.description]
    return [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]


def build(con: duckdb.DuckDBPyConnection) -> Graph:
    graph = Graph()
    graph.nodes["Product"] = [
        {k: v for k, v in row.items() if k != "brand"} for row in _rows(con, PRODUCTS_SQL)
    ]
    for label, query in NODE_QUERIES.items():
        graph.nodes[label] = _rows(con, query)
    for kind, query in EDGE_QUERIES.items():
        graph.edges[kind] = _rows(con, query)
    from pipeline.load.serving import _meta

    graph.snapshot_date = _meta(con)["snapshot_date"]
    return graph


def check(graph: Graph, max_nodes: int = MAX_NODES, max_rels: int = MAX_RELATIONSHIPS) -> None:
    """Refuse a graph over the caps, before any connection is made."""
    limit_nodes = min(max_nodes, AURA_FREE_NODES)
    limit_rels = min(max_rels, AURA_FREE_RELATIONSHIPS)
    if graph.node_count > limit_nodes or graph.relationship_count > limit_rels:
        raise SystemExit(
            f"{graph.node_count:,} nodes and {graph.relationship_count:,} relationships pass "
            f"the caps ({limit_nodes:,} and {limit_rels:,}). Not loading."
        )


def report(graph: Graph, log: Log = print) -> None:
    for label, rows in graph.nodes.items():
        log(f"  {label:<16} {len(rows):>9,} nodes")
    for kind, rows in graph.edges.items():
        log(f"  {kind:<16} {len(rows):>9,} relationships")
    log(
        f"  {'total':<16} {graph.node_count:>9,} nodes (cap {MAX_NODES:,}), "
        f"{graph.relationship_count:,} relationships (cap {MAX_RELATIONSHIPS:,})"
    )


def _batches(rows: Sequence[dict[str, Any]], size: int = BATCH) -> Iterator[Sequence[dict]]:
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def write(driver: Any, graph: Graph, log: Log = print) -> None:
    """Replace the graph in Neo4j: clear, constrain, create nodes, then relationships."""
    started = time.perf_counter()
    with driver.session() as session:
        session.run(
            "MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS"
        ).consume()
        for label, key in KEYS.items():
            session.run(
                f"CREATE CONSTRAINT {label.lower()}_{key} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{key} IS UNIQUE"
            ).consume()
        log(f"Cleared the old graph in {time.perf_counter() - started:.0f} s.")

        for label, rows in graph.nodes.items():
            query = f"UNWIND $rows AS r CREATE (n:{label}) SET n = r"
            for chunk in _batches(rows):
                session.execute_write(lambda tx, q=query, c=chunk: tx.run(q, rows=c).consume())
        for kind, rows in graph.edges.items():
            src, src_key, dst, dst_key = EDGE_ENDS[kind]
            props = " {rank: r.rank}" if kind == "HAS_INGREDIENT" else ""
            query = (
                f"UNWIND $rows AS r MATCH (a:{src} {{{src_key}: r.source}}) "
                f"MATCH (b:{dst} {{{dst_key}: r.target}}) CREATE (a)-[:{kind}{props}]->(b)"
            )
            for chunk in _batches(rows):
                session.execute_write(lambda tx, q=query, c=chunk: tx.run(q, rows=c).consume())
        session.run(
            "CREATE (:Meta {snapshot_date: $date, loaded_at: $at, nodes: $nodes, "
            "relationships: $rels})",
            date=graph.snapshot_date,
            at=datetime.now(UTC).isoformat(timespec="seconds"),
            nodes=graph.node_count,
            rels=graph.relationship_count,
        ).consume()
    log(f"Loaded the graph in {time.perf_counter() - started:.0f} s.")


def connect(uri: str, user: str, password: str) -> Any:
    from api.app.graph import make_driver

    driver = make_driver(uri, user, password)
    driver.verify_connectivity()
    return driver


def _driver_from_settings() -> Any | None:
    from api.app.config import get_settings

    settings = get_settings()
    if not (settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password):
        print("No graph database: set NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD.", file=sys.stderr)
        return None
    return connect(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )


def ping() -> int:
    """One read: AuraDB Free pauses after 72 idle hours (see graph-keepalive.yml)."""
    driver = _driver_from_settings()
    if driver is None:
        return 1
    try:
        with driver.session() as session:
            row = session.run("MATCH (m:Meta) RETURN m.loaded_at AS at LIMIT 1").single()
        print(f"Graph awake; loaded at {row['at'] if row else 'unknown'}.")
    finally:
        driver.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the food graph into Neo4j.")
    parser.add_argument("--duckdb", type=Path, default=DUCKDB_PATH)
    parser.add_argument("--dry-run", action="store_true", help="print the counts only")
    parser.add_argument("--ping", action="store_true", help="read one node and exit")
    args = parser.parse_args(argv)

    if args.ping:
        return ping()

    import duckdb

    with duckdb.connect(str(args.duckdb), read_only=True) as con:
        graph = build(con)
    report(graph)
    check(graph)
    if args.dry_run:
        return 0

    from api.app.config import get_settings

    settings = get_settings()
    if not (settings.neo4j_uri and settings.neo4j_user and settings.neo4j_password):
        print("No graph database: set NEO4J_URI, NEO4J_USER and NEO4J_PASSWORD.", file=sys.stderr)
        return 1
    driver = connect(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password.get_secret_value()
    )
    try:
        write(driver, graph)
    finally:
        driver.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
