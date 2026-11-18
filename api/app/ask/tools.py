"""The ask agent's three tools, and the citation ids their results carry.

- query_sql: one SELECT (or WITH) on the serving tables, as the read-only role, inside a
  read-only transaction with a 3-second statement timeout, wrapped so at most 50 rows return.
- query_graph: fixed, parameterised Cypher templates on the Neo4j graph. No free-form Cypher.
  `swaps` runs the product page's own swap rule (Postgres), so the agent and the page agree.
- search_explainers: the question embedded by Voyage (input_type=query), then the five
  nearest explainers by cosine distance in pgvector.

Every row, node or explainer a tool returns gets a citation id (R1, N1, E1...). The model
cites those ids; the agent maps them to links and drops any id no tool handed out.

A ToolError is a problem the model can fix (bad SQL, unknown product, graph paused): its
message goes back as an error tool result. A database that cannot answer at all raises
through, and the run ends with `tool_failed`.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

import psycopg

from api.app.db import DictConnection
from api.app.embeddings import EmbeddingsUnavailable, Voyage, vector_literal
from api.app.graph import Graph, GraphUnavailable
from api.app.swaps import find_swaps

ROW_LIMIT = 50
STATEMENT_TIMEOUT = "3s"
MAX_TEXT = 300
MAX_LIST = 12
EXPLAINER_TOP = 5
GRAPH_LIMIT = 15
SWAP_LIMIT = 5

ToolName = Literal["query_sql", "query_graph", "search_explainers"]
TOOL_NAMES: tuple[ToolName, ...] = ("query_sql", "query_graph", "search_explainers")
CiteKind = Literal["row", "node", "explainer"]
_PREFIX: dict[CiteKind, str] = {"row": "R", "node": "N", "explainer": "E"}


class ToolError(Exception):
    """A failure the model can act on. The message is written for the model."""


# --- Citations -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Cite:
    id: str
    kind: CiteKind
    ref: str
    label: str
    url: str | None


@dataclass
class Citations:
    """Ids handed out during one run. The same thing cited twice keeps its first id."""

    _by_key: dict[tuple[str, str], Cite] = field(default_factory=dict)
    _by_id: dict[str, Cite] = field(default_factory=dict)

    def add(self, kind: CiteKind, ref: str, label: str, url: str | None) -> str:
        key = (kind, ref)
        if key not in self._by_key:
            n = sum(1 for k, _ in self._by_key if k == kind) + 1
            cite = Cite(f"{_PREFIX[kind]}{n}", kind, ref, label, url)
            self._by_key[key] = cite
            self._by_id[cite.id] = cite
        return self._by_key[key].id

    def get(self, cite_id: str) -> Cite | None:
        return self._by_id.get(cite_id)

    def __len__(self) -> int:
        return len(self._by_id)


def product_url(code: str) -> str:
    return f"/products/{code}"


def explorer_url(code: str) -> str:
    return f"/graph?code={code}"


# --- Results -------------------------------------------------------------------------------


@dataclass
class ToolResult:
    tool: ToolName
    summary: str
    content: str  # JSON, for the model
    row_count: int
    duration_ms: int
    is_error: bool = False
    embedding_tokens: int = 0


def trim(value: Any) -> Any:
    """Keep tool results small: long text cut, long lists shortened, numbers rounded."""
    if isinstance(value, str):
        return value if len(value) <= MAX_TEXT else value[:MAX_TEXT] + "…"
    if isinstance(value, list | tuple):
        items = [trim(v) for v in value[:MAX_LIST]]
        if len(value) > MAX_LIST:
            items.append(f"… {len(value) - MAX_LIST} more")
        return items
    if isinstance(value, dict):
        return {k: trim(v) for k, v in value.items()}
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, Decimal):
        return float(round(value, 3))
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


# --- query_sql -----------------------------------------------------------------------------

_COMMENT = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
_READABLE = "serving.products, additives, ingredients, categories and explainers"


def check_sql(text: str) -> str:
    """One SELECT or WITH statement, without a trailing semicolon. Raises ToolError."""
    statement = text.strip().rstrip(";").strip()
    if not statement:
        raise ToolError("The query is empty.")
    if ";" in statement:
        raise ToolError("Send one statement only, without semicolons.")
    if not re.match(r"(select|with)\b", _COMMENT.sub(" ", statement).lstrip(), re.I):
        raise ToolError("Only SELECT or WITH queries can run. The data is read-only.")
    return statement


def _readonly_transaction(conn: DictConnection) -> None:
    conn.execute("set transaction read only")
    conn.execute(f"set local statement_timeout = '{STATEMENT_TIMEOUT}'")
    conn.execute("set local search_path = serving")


def _sql_error(error: psycopg.Error) -> ToolError:
    if isinstance(error, psycopg.errors.QueryCanceled):
        return ToolError(
            f"The query ran past {STATEMENT_TIMEOUT} and was stopped. Narrow it: filter on "
            "category_id or nutriscore_grade, avoid unanchored ILIKE on every row, or "
            "aggregate fewer rows."
        )
    if isinstance(error, psycopg.errors.InsufficientPrivilege):
        return ToolError(f"Permission denied. Only {_READABLE} can be read.")
    if isinstance(error, psycopg.errors.ReadOnlySqlTransaction):
        return ToolError("The data is read-only. Only SELECT queries can run.")
    diag = error.diag
    detail = diag.message_primary or str(error).splitlines()[0]
    hint = f" Hint: {diag.message_hint}" if diag.message_hint else ""
    return ToolError(f"SQL error: {detail}.{hint}")


def _row_label(row: dict[str, Any]) -> str:
    name, brand = row.get("name"), row.get("brand")
    if name and brand:
        return f"{name} ({brand})"
    return str(name or row.get("code"))


# --- query_graph ---------------------------------------------------------------------------

GRAPH_TEMPLATES = ("swaps", "products_sharing_additive", "shared_ingredients",
                   "category_neighbours")  # fmt: skip

SHARING_ADDITIVE = """
MATCH (a:Additive)
WHERE a.id = $additive OR toLower(a.e_number) = toLower($additive)
   OR toLower(a.name) = toLower($additive)
WITH a LIMIT 1
CALL (a) {
    OPTIONAL MATCH (p:Product)-[:CONTAINS]->(a)
    WHERE $category IS NULL OR p.category = $category
    WITH p ORDER BY p.rank
    RETURN count(p) AS total,
           collect(p {.code, .name, .grade, .category})[..$limit] AS products
}
RETURN a {.id, .name, .e_number, .function, .flagged} AS additive, total, products
"""

SHARED_INGREDIENTS = """
MATCH (p:Product {code: $code})
CALL (p) {
    OPTIONAL MATCH (p)-[:HAS_INGREDIENT]->(i:Ingredient)<-[:HAS_INGREDIENT]-(o:Product)
    WHERE o.category = p.category AND o <> p
    WITH o, collect(i.name) AS shared
    WHERE o IS NOT NULL
    ORDER BY size(shared) DESC, o.rank
    LIMIT $limit
    RETURN collect(o {.code, .name, .grade, shared_count: size(shared),
                      shared: shared[..8]}) AS similar
}
RETURN p {.code, .name, .grade, .category} AS product,
       COUNT { (p)-[:HAS_INGREDIENT]->() } AS ingredient_count, similar
"""

CATEGORY_NEIGHBOURS = """
MATCH (c:Category)
WHERE c.id = $category OR toLower(c.name) = toLower($category)
WITH c LIMIT 1
CALL (c) {
    OPTIONAL MATCH (c)-[:CHILD_OF]->(parent:Category)
    RETURN parent {.id, .name} AS parent
}
CALL (c) {
    OPTIONAL MATCH (child:Category)-[:CHILD_OF]->(c)
    RETURN collect(child {.id, .name, products: COUNT { (child)<-[:IN]-() }}) AS children
}
CALL (c) {
    OPTIONAL MATCH (c)-[:CHILD_OF]->(:Category)<-[:CHILD_OF]-(s:Category)
    WHERE s <> c
    RETURN collect(s {.id, .name, products: COUNT { (s)<-[:IN]-() }}) AS siblings
}
CALL (c) {
    OPTIONAL MATCH (c)<-[:CHILD_OF*0..1]-(:Category)<-[:IN]-(p:Product)-[:CONTAINS]->(a:Additive)
    WITH a, count(DISTINCT p) AS n
    WHERE a IS NOT NULL
    ORDER BY n DESC, a.id
    LIMIT 8
    RETURN collect(a {.id, .name, .e_number, .flagged, products: n}) AS top_additives
}
RETURN c {.id, .name} AS category,
       COUNT { (c)<-[:CHILD_OF*0..1]-(:Category)<-[:IN]-(:Product) } AS products,
       parent, children, siblings, top_additives
"""

GRAPH_NOTE = (
    "The graph holds a subset: the best-ranked graded products (about 28,000 of 676,000), so "
    "counts here cover only those. Use query_sql for counts over all products."
)


def _digits(code: str | None) -> str:
    digits = re.sub(r"\D", "", code or "")
    if not digits:
        raise ToolError("This template needs `code`: the product's barcode, digits only.")
    return digits


# --- The tools -----------------------------------------------------------------------------

Connect = Callable[[], AbstractContextManager[DictConnection]]


@dataclass
class Tools:
    """The tools for one run. `connect` lends a read-only connection (autocommit, dict rows)."""

    connect: Connect
    graph: Graph
    voyage: Voyage
    citations: Citations = field(default_factory=Citations)
    _queries: int = 0

    def run(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        started = time.perf_counter()
        summary = str(arguments.get("summary") or "").strip()[:160] or _default_summary(name)
        tool: ToolName = name if name in TOOL_NAMES else "query_sql"  # type: ignore[assignment]
        embedding_tokens = 0
        try:
            if name == "query_sql":
                data, count = self.query_sql(str(arguments.get("sql") or ""))
            elif name == "query_graph":
                data, count = self.query_graph(arguments)
            elif name == "search_explainers":
                data, count, embedding_tokens = self.search_explainers(
                    str(arguments.get("query") or "")
                )
            else:
                raise ToolError(f"There is no tool called {name}.")
        except ToolError as error:
            return ToolResult(tool, summary, _json({"error": str(error)}), 0,
                              _ms(started), is_error=True)  # fmt: skip
        return ToolResult(tool, summary, _json(data), count, _ms(started),
                          embedding_tokens=embedding_tokens)  # fmt: skip

    # query_sql

    def query_sql(self, text: str) -> tuple[dict[str, Any], int]:
        statement = check_sql(text)
        wrapped = f"select * from (\n{statement}\n) as q limit {ROW_LIMIT + 1}"
        with self.connect() as conn:
            try:
                with conn.transaction():
                    _readonly_transaction(conn)
                    rows = conn.execute(wrapped).fetchall()  # type: ignore[arg-type]
            except psycopg.Error as error:
                # A lost connection is the database itself, not something the model can fix.
                # (QueryCanceled is an OperationalError too, but it is the model's query.)
                lost = isinstance(error, psycopg.OperationalError) and not isinstance(
                    error, psycopg.errors.QueryCanceled
                )
                if lost:
                    raise
                raise _sql_error(error) from None
        truncated = len(rows) > ROW_LIMIT
        rows = rows[:ROW_LIMIT]
        out: list[dict[str, Any]] = []
        whole: str | None = None
        for row in rows:
            item = {k: trim(v) for k, v in row.items()}
            if row.get("code"):
                code = str(row["code"])
                item["cite"] = self.citations.add("row", code, _row_label(row), product_url(code))
            else:
                if whole is None:  # an aggregate: one id for the whole result
                    self._queries += 1
                    whole = self.citations.add("row", f"query:{self._queries}", "Query result",
                                               None)  # fmt: skip
                item["cite"] = whole
            out.append(item)
        data: dict[str, Any] = {"rows": out, "row_count": len(out)}
        if truncated:
            data["note"] = f"More rows matched; only the first {ROW_LIMIT} are shown."
        return data, len(out)

    # query_graph

    def query_graph(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], int]:
        template = arguments.get("template")
        if template not in GRAPH_TEMPLATES:
            raise ToolError(f"Unknown template. Use one of: {', '.join(GRAPH_TEMPLATES)}.")
        if template == "swaps":
            return self._swaps(_digits(arguments.get("code")))
        try:
            if template == "products_sharing_additive":
                return self._sharing_additive(arguments)
            if template == "shared_ingredients":
                return self._shared_ingredients(_digits(arguments.get("code")))
            return self._category_neighbours(arguments)
        except GraphUnavailable:
            raise ToolError(
                "The graph is not available right now. Answer with query_sql instead."
            ) from None

    def _swaps(self, code: str) -> tuple[dict[str, Any], int]:
        with self.connect() as conn, conn.transaction():
            _readonly_transaction(conn)
            found = find_swaps(conn, code, SWAP_LIMIT)
        if found is None:
            raise ToolError(f"No product has the barcode {code}. Find it with query_sql first.")
        swaps = []
        for swap in found:
            product = swap["product"]
            cite = self.citations.add(
                "row", product["code"], _row_label(product), product_url(product["code"])
            )
            swaps.append({
                "code": product["code"], "name": product["name"], "brand": product["brand"],
                "nutriscore_grade": product["nutriscore_grade"], "reason": swap["reason"],
                "cite": cite,
            })  # fmt: skip
        data: dict[str, Any] = {"code": code, "swaps": swaps}
        if not swaps:
            data["note"] = (
                "No swaps: none in the same category with a similar name, a better "
                "Nutri-Score and no additive Open Food Facts flags as high risk."
            )
        return data, len(swaps)

    def _product_node(self, product: dict[str, Any]) -> dict[str, Any]:
        code = product["code"]
        cite = self.citations.add("node", f"Product:{code}", product["name"], explorer_url(code))
        return {**trim(product), "cite": cite}

    def _sharing_additive(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], int]:
        additive = str(arguments.get("additive") or "").strip()
        if not additive:
            raise ToolError("This template needs `additive`: an id (en:e330), E-number or name.")
        category = arguments.get("category") or None
        rows = self.graph.read(SHARING_ADDITIVE, additive=additive, category=category,
                               limit=GRAPH_LIMIT)  # fmt: skip
        if not rows:
            raise ToolError(f"No additive matches {additive!r}. Try its E-number, like E330.")
        row = rows[0]
        a = row["additive"]
        label = f"{a['e_number']} {a['name']}" if a.get("e_number") else a["name"]
        a["cite"] = self.citations.add("node", f"Additive:{a['id']}", label, None)
        products = [self._product_node(p) for p in row["products"]]
        data = {"additive": a, "products_in_graph": row["total"], "products": products,
                "note": GRAPH_NOTE}  # fmt: skip
        return data, len(products)

    def _shared_ingredients(self, code: str) -> tuple[dict[str, Any], int]:
        rows = self.graph.read(SHARED_INGREDIENTS, code=code, limit=GRAPH_LIMIT)
        if not rows:
            raise ToolError(
                f"The graph does not hold {code}: it has only the best-ranked graded products. "
                "Use query_sql (ingredient_ids) instead."
            )
        row = rows[0]
        similar = [self._product_node(p) for p in row["similar"]]
        data = {"product": self._product_node(row["product"]),
                "ingredient_count": row["ingredient_count"], "similar_in_category": similar,
                "note": GRAPH_NOTE}  # fmt: skip
        return data, len(similar)

    def _category_neighbours(self, arguments: dict[str, Any]) -> tuple[dict[str, Any], int]:
        category = str(arguments.get("category") or "").strip()
        if not category:
            raise ToolError("This template needs `category`: an id such as breakfast-cereals.")
        rows = self.graph.read(CATEGORY_NEIGHBOURS, category=category)
        if not rows:
            raise ToolError(f"No category matches {category!r}. Use an id from query_sql.")
        row = rows[0]
        c = row["category"]
        c["cite"] = self.citations.add("node", f"Category:{c['id']}", c["name"], None)
        for a in row["top_additives"]:
            label = f"{a['e_number']} {a['name']}" if a.get("e_number") else a["name"]
            a["cite"] = self.citations.add("node", f"Additive:{a['id']}", label, None)
        data = {**{k: v for k, v in row.items() if k != "category"}, "category": c,
                "products_in_graph": row["products"], "note": GRAPH_NOTE}  # fmt: skip
        data.pop("products", None)
        count = 1 + len(row["children"]) + len(row["siblings"]) + len(row["top_additives"])
        return data, count

    # search_explainers

    def search_explainers(self, query: str) -> tuple[dict[str, Any], int, int]:
        query = query.strip()
        if len(query) < 3:
            raise ToolError("Give a query of a few words, like 'what is carrageenan'.")
        try:
            embedded = self.voyage.embed([query[:500]], input_type="query")
        except EmbeddingsUnavailable:
            raise ToolError(
                "Explainer search is not available right now. Use query_sql on "
                "additives.explainer or ingredients.explainer instead."
            ) from None
        with self.connect() as conn, conn.transaction():
            _readonly_transaction(conn)
            rows = conn.execute(
                """select id, kind, name, text,
                              embedding operator(public.<=>) %s::public.vector as distance
                       from serving.explainers order by distance limit %s""",
                [vector_literal(embedded.vectors[0]), EXPLAINER_TOP],
            ).fetchall()
        results = []
        for row in rows:
            cite = self.citations.add("explainer", row["id"], row["name"], None)
            results.append({
                "id": row["id"], "kind": row["kind"], "name": row["name"], "text": row["text"],
                "distance": round(float(row["distance"]), 3), "cite": cite,
            })  # fmt: skip
        note = "Explainers are AI-written summaries; say so when you use one."
        return {"results": results, "note": note}, len(results), embedded.tokens


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _default_summary(name: str) -> str:
    return {
        "query_sql": "Queried the product tables",
        "query_graph": "Looked up the food graph",
        "search_explainers": "Searched the additive and ingredient explainers",
    }.get(name, "Used a tool")


def iter_cites(text: str) -> Iterator[str]:
    """Citation ids in an answer, in order of first appearance: [R1], [N2, E1]..."""
    seen: set[str] = set()
    for group in re.findall(r"\[([RNE]\d+(?:\s*,\s*[RNE]\d+)*)\]", text):
        for cite_id in re.split(r"\s*,\s*", group):
            if cite_id not in seen:
                seen.add(cite_id)
                yield cite_id
