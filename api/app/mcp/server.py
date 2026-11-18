"""The LabelLens MCP server, mounted on the API at /mcp.

Public, read-only and unauthenticated by design (docs/decisions/0008-mcp-app.md): every tool
reads the same serving tables the website shows. Stateless streamable HTTP: a 2026-07-28 client
needs no session at all, and `stateless_http` gives older clients the same, so either Cloud Run
instance can answer any request.

Tools are plain sync functions over the API's connection pool; the SDK runs them in a worker
thread, as FastAPI does for the routes.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, ContentBlock, TextContent, ToolAnnotations
from pydantic import Field
from starlette.routing import BaseRoute, Route

from api.app import search as search_module
from api.app.db import Database, DictConnection
from api.app.mcp.models import Listed, SearchOutput
from api.app.schemas import Source

PATH = "/mcp"
GRADES = {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"}
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

INSTRUCTIONS = """\
LabelLens explains US packaged-food labels from Open Food Facts: Nutri-Score, NOVA processing \
group, nutrients per 100 g, additives and ingredients, and better swaps in the same category.

To look at a product you only know by name, call search_products first and use the barcode it \
returns. LabelLens shows label facts; it does not give medical or dietary advice."""


class McpApp:
    """The server plus the one route the API mounts."""

    def __init__(self, server: MCPServer, route: BaseRoute):
        self.server = server
        self.route = route


def _attribution(source: Source) -> str:
    day = source.snapshot_date
    when = f", snapshot of {day:%B} {day.day}, {day.year}" if day else ""
    return f"Data: Open Food Facts, under the Open Database License (ODbL){when}."


def _grade(grade: str | None) -> str:
    return f"Nutri-Score {GRADES[grade]}" if grade else "no Nutri-Score"


def _named(product: Listed) -> str:
    name = product.name or "Unnamed product"
    return f"{name} ({product.brand})" if product.brand else name


def _text(*lines: str) -> list[ContentBlock]:
    return [TextContent(type="text", text="\n".join(lines))]


def create_mcp(get_db: Callable[[], Database], web_url: str) -> McpApp:
    """The MCP server over the app's database. `get_db` is read per call (the pool opens with
    the app's lifespan, after this runs)."""
    web_url = web_url.rstrip("/")
    server = MCPServer("LabelLens", instructions=INSTRUCTIONS, website_url=web_url)

    def page(code: str) -> str:
        return f"{web_url}/product/{code}"

    def source() -> Source:
        return Source(snapshot_date=get_db().snapshot_date())

    def listed(row: dict[str, Any]) -> Listed:
        fields = {k: v for k, v in row.items() if k != "match"}
        return Listed(**fields, url=page(row["code"]))

    @server.tool(
        title="Search products",
        description=(
            "Find US packaged-food products by name, brand or barcode. Returns the best-known "
            "matches first, each with its barcode, brand and Nutri-Score. Use it before "
            "get_product or find_swaps when you only know a product's name."
        ),
        annotations=READ_ONLY,
    )
    def search_products(
        query: Annotated[
            str,
            Field(
                min_length=1,
                max_length=200,
                description="Product name, brand or barcode, e.g. 'honey nut cheerios'.",
            ),
        ],
        limit: Annotated[int, Field(ge=1, le=10, description="How many results, 1 to 10.")] = 5,
    ) -> Annotated[CallToolResult, SearchOutput]:
        with _connection(get_db()) as conn:
            rows = search_module.search(conn, query, limit)
        results = [listed(r) for r in rows]
        src = source()
        if not results:
            raise ToolError(
                f"No products match {query!r}. Try fewer words, the brand, or the barcode."
            )
        lines = [f"{len(results)} products matching {query!r}, best known first:"]
        lines += [
            f"{i}. {_named(p)}, barcode {p.code}, {_grade(p.nutriscore_grade)}. {p.url}"
            for i, p in enumerate(results, 1)
        ]
        output = SearchOutput(query=query, results=results, source=src)
        return CallToolResult(
            content=_text(*lines, "", _attribution(src)),
            structured_content=output.model_dump(mode="json"),
        )

    app = server.streamable_http_app(
        streamable_http_path=PATH,
        stateless_http=True,
        json_response=True,
        # No host or origin check: the server is public, unauthenticated and read-only, sets
        # no cookies and holds no session, so a DNS-rebinding page could only read what anyone
        # can. Cloud Run routes only its own hostnames to the service.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    sdk_route = next(r for r in app.routes if isinstance(r, Route) and r.path == PATH)
    # The SDK's handler on a route of our own: the methods MCP uses, and out of the generated
    # OpenAPI (docs/openapi.yaml documents /mcp by hand).
    route = Route(
        PATH,
        endpoint=sdk_route.endpoint,
        methods=["GET", "POST", "DELETE"],
        include_in_schema=False,
    )
    return McpApp(server, route)


def _connection(db: Database) -> AbstractContextManager[DictConnection]:
    """One pooled connection for one tool call."""
    return contextmanager(db.connection)()
