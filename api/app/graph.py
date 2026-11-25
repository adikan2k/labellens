"""The food graph in Neo4j: a product's neighbourhood for the explorer.

Depth 1 is the product and what it links to: its brand, category (with the category's
parent), additives and ingredients. Depth 2 adds other products through each of those
nodes, the best-ranked few per node, so a hub such as sugar (thousands of products) adds a
handful, not thousands. The whole neighbourhood is capped at MAX_NODES; `truncated` says
whether anything was left out.

Each brand, category, additive and ingredient linked to the product also carries its
`degree`: how many links point to it in the whole graph, nearly all from products. The
explorer uses it to count a shared rare thing for more than shared salt.

Node ids carry their kind ("Product:0016000275287", "Brand:general mills") so ids from
different kinds never collide. The graph is optional: without NEO4J_* settings, or while
AuraDB Free is paused or reloading, requests get a 503.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_NODES = 150
PER_HUB = 6
# Hubs at depth 2, in the order their products are added while room remains.
HUB_ORDER = ("Brand", "Category", "Additive", "Ingredient")
KINDS = ("Product", "Brand", "Category", "Additive", "Ingredient")

# One round trip: the product's links, its category's parent and, at depth 2, the hubs with
# their best-ranked other products. (Two queries cost a second trip from Cloud Run to Aura.)
NEIGHBORHOOD_QUERY = """
MATCH (p:Product {code: $code})
CALL (p) {
    OPTIONAL MATCH (p)-[r]->(n)
    RETURN collect(CASE WHEN n IS NULL THEN null ELSE {
        type: type(r), rank: r.rank, label: labels(n)[0], key: coalesce(n.code, n.id),
        name: n.name, grade: n.grade, e_number: n.e_number, explainer: n.explainer
    } END) AS links
}
CALL (p) {
    OPTIONAL MATCH (p)-[:IN]->(:Category)-[:CHILD_OF]->(parent:Category)
    RETURN parent {.id, .name} AS parent
}
CALL (p) {
    OPTIONAL MATCH (p)-[]->(n)
    WHERE $depth >= 2
    CALL (p, n) {
        OPTIONAL MATCH (o:Product)-[r]->(n)
        WHERE o <> p
        WITH o, type(r) AS type
        ORDER BY o.rank
        LIMIT $per_hub
        RETURN collect(CASE WHEN o IS NULL THEN null ELSE
            {code: o.code, name: o.name, grade: o.grade, type: type} END) AS others
    }
    RETURN collect(CASE WHEN n IS NULL THEN null ELSE {
        label: labels(n)[0], key: coalesce(n.code, n.id), degree: COUNT { (n)<--() },
        others: others
    } END) AS hubs
}
RETURN p {.code, .name, .grade} AS product, links, parent, hubs
"""


def make_driver(uri: str, user: str, password: str, **config: Any) -> Any:
    """A Neo4j driver that trusts the Mozilla CA bundle (certifi) for encrypted connections.

    AuraDB's certificate chains to an SSL.com root that a Windows certificate store may not
    have installed yet, so the system store fails there while certifi verifies it. One trust
    source everywhere (Windows, Linux, CI). `neo4j+s://` becomes `neo4j://` with encryption
    on, since the driver only takes a custom trust store without the +s shorthand. Local
    `bolt://` addresses are unchanged.
    """
    from neo4j import GraphDatabase, TrustCustomCAs

    scheme, sep, rest = uri.partition("://")
    if sep and scheme.endswith("+s"):
        import certifi

        uri = f"{scheme[:-2]}://{rest}"
        config |= {"encrypted": True, "trusted_certificates": TrustCustomCAs(certifi.where())}
    return GraphDatabase.driver(uri, auth=(user, password), **config)


class GraphUnavailable(RuntimeError):
    """Not configured, or AuraDB is paused, reloading or unreachable."""


def node_id(kind: str, key: str) -> str:
    return f"{kind}:{key}"


def _product_node(nid: str, product: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": nid,
        "kind": "Product",
        "name": product["name"],
        "nutriscore_grade": product.get("grade"),
        "detail": None,
        "degree": None,
    }


def assemble(
    center: dict[str, Any], hubs: list[dict[str, Any]] | None, max_nodes: int = MAX_NODES
) -> dict[str, Any]:
    """The contract's GraphNeighborhood (without source) from plain query results."""
    product = center["product"]
    center_id = node_id("Product", product["code"])
    nodes: dict[str, dict[str, Any]] = {center_id: _product_node(center_id, product)}
    edges: list[dict[str, str]] = []

    links = sorted(
        (link for link in center["links"] if link and link["label"] in KINDS),
        key=lambda link: (HUB_ORDER.index(link["label"]), link.get("rank") or 0),
    )
    for link in links:
        nid = node_id(link["label"], link["key"])
        nodes.setdefault(nid, {
            "id": nid,
            "kind": link["label"],
            "name": f"{link['e_number']} {link['name']}" if link.get("e_number") else link["name"],
            "nutriscore_grade": None,
            "detail": link.get("explainer"),
            "degree": None,
        })  # fmt: skip
        edges.append({"from": center_id, "to": nid, "type": link["type"]})
    parent = center.get("parent")
    category = next((link for link in links if link["label"] == "Category"), None)
    if parent and category:
        pid = node_id("Category", parent["id"])
        nodes.setdefault(pid, {"id": pid, "kind": "Category", "name": parent["name"],
                               "nutriscore_grade": None, "detail": None,
                               "degree": None})  # fmt: skip
        edges.append({"from": node_id("Category", category["key"]), "to": pid, "type": "CHILD_OF"})

    truncated = False
    if hubs is not None:
        hubs = sorted(
            hubs, key=lambda h: HUB_ORDER.index(h["label"]) if h["label"] in HUB_ORDER else 9
        )
        for hub in hubs:
            hub_id = node_id(hub["label"], hub["key"])
            if hub_id in nodes:
                nodes[hub_id]["degree"] = hub["degree"]
            if hub["degree"] - 1 > len(hub["others"]):
                truncated = True
            for other in hub["others"]:
                oid = node_id("Product", other["code"])
                if oid not in nodes:
                    if len(nodes) >= max_nodes:
                        truncated = True
                        continue
                    nodes[oid] = _product_node(oid, other)
                edges.append({"from": oid, "to": hub_id, "type": other["type"]})

    return {"center": center_id, "nodes": list(nodes.values()), "edges": edges,
            "truncated": truncated}  # fmt: skip


@dataclass
class Graph:
    driver: Any | None

    @classmethod
    def open(cls, uri: str | None, user: str | None, password: str | None) -> Graph:
        if not (uri and user and password):
            return cls(driver=None)
        # Lazy: no connection is made until the first query, so a paused instance does not
        # stop the API from starting.
        return cls(driver=make_driver(uri, user, password, connection_timeout=8))

    def close(self) -> None:
        if self.driver is not None:
            self.driver.close()

    def read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if self.driver is None:
            raise GraphUnavailable("NEO4J_* is not set")
        from neo4j import RoutingControl
        from neo4j.exceptions import DriverError, Neo4jError

        try:
            records, _, _ = self.driver.execute_query(
                query, parameters_=params, routing_=RoutingControl.READ
            )
        except (DriverError, Neo4jError) as error:
            raise GraphUnavailable(str(error)) from error
        return [record.data() for record in records]

    def neighborhood(self, code: str, depth: int) -> dict[str, Any] | None:
        """The neighbourhood, or None if the graph does not hold this product."""
        rows = self.read(NEIGHBORHOOD_QUERY, code=code, depth=depth, per_hub=PER_HUB)
        if not rows:
            return None
        row = rows[0]
        return assemble(row, row["hubs"] if depth >= 2 else None)
