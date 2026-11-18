"""The LabelLens MCP server, mounted on the API at /mcp.

Public, read-only and unauthenticated by design (docs/decisions/0008-mcp-app.md): every tool
reads the same serving tables the website shows. Stateless streamable HTTP: a 2026-07-28 client
needs no session at all, and `stateless_http` gives older clients the same, so either Cloud Run
instance can answer any request.

Tools are plain sync functions over the API's connection pool; the SDK runs them in a worker
thread, as FastAPI does for the routes. Each returns readable text for the model (api/app/mcp/
text.py) and structured content for the card (api/app/mcp/models.py).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Annotated, Any

from mcp.server.apps import Apps, ResourceCsp
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import CallToolResult, ContentBlock, TextContent, ToolAnnotations
from pydantic import Field
from starlette.routing import BaseRoute, Route

from api.app import additives as additives_module
from api.app import products as products_module
from api.app import search as search_module
from api.app import swaps as swaps_module
from api.app.db import Database, DictConnection
from api.app.mcp import text
from api.app.mcp.limit import RateLimited
from api.app.mcp.models import (
    AdditiveOutput,
    CardAdditive,
    CardProduct,
    CardSwap,
    Listed,
    ProductOutput,
    SearchOutput,
    SwapsOutput,
)
from api.app.schemas import Explainer, Nutrition, Source

PATH = "/mcp"
CARD_URI = "ui://labellens/label-card.html"
CARD_HTML = (Path(__file__).parent / "card.html").read_text("utf-8")
FONT_HOSTS = ["https://fonts.googleapis.com", "https://fonts.gstatic.com"]
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)

INSTRUCTIONS = """\
LabelLens explains US packaged-food labels from Open Food Facts: Nutri-Score, NOVA processing \
group, nutrients per 100 g, additives, and better swaps in the same category.

To look at a product you only know by name, call search_products first and use the barcode it \
returns. When someone wants something better, healthier or similar to a product, call \
find_swaps directly: it already includes that product. LabelLens shows label facts; it does \
not give medical or dietary advice."""

Barcode = Annotated[
    str,
    Field(
        min_length=6,
        max_length=32,
        description="The product's barcode (EAN or UPC), digits only, from search_products.",
    ),
]


class McpApp:
    """The server plus the one route the API mounts."""

    def __init__(self, server: MCPServer, route: BaseRoute):
        self.server = server
        self.route = route


def _content(body: str) -> list[ContentBlock]:
    return [TextContent(type="text", text=body)]


def _result(body: str, output: Any) -> CallToolResult:
    return CallToolResult(content=_content(body), structured_content=output.model_dump(mode="json"))


def _codes(code: str) -> list[str]:
    """A 12-digit UPC is stored as a 13-digit EAN with a leading zero."""
    digits = "".join(ch for ch in code if ch.isdigit())
    return [digits, f"0{digits}"] if len(digits) == 12 else [digits]


def create_mcp(get_db: Callable[[], Database], web_url: str, *, per_minute: int = 60) -> McpApp:
    """The MCP server over the app's database. `get_db` is read per call (the pool opens with
    the app's lifespan, after this runs)."""
    web_url = web_url.rstrip("/")
    # get_product and find_swaps render the label card (MCP Apps); the other two are text.
    # UI-bound tools go on the extension before the server exists; plain ones are collected
    # and registered after it.
    apps = Apps()
    apps.add_html_resource(
        CARD_URI,
        CARD_HTML,
        name="label-card",
        title="LabelLens label card",
        description="A compact product label, or a product's better swaps.",
        csp=ResourceCsp(resource_domains=FONT_HOSTS),
        prefers_border=False,  # the card draws its own 2 px panel border
    )
    plain: list[tuple[Callable[..., Any], dict[str, Any]]] = []

    def tool(**kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def register(fn: Callable[..., Any]) -> Callable[..., Any]:
            plain.append((fn, kwargs))
            return fn

        return register

    def page(code: str) -> str:
        return f"{web_url}/product/{code}"

    def source() -> Source:
        return Source(snapshot_date=get_db().snapshot_date())

    def listed(row: dict[str, Any]) -> Listed:
        fields = {k: row[k] for k in Listed.model_fields if k in row}
        return Listed(**fields, url=page(row["code"]))

    def product_row(conn: DictConnection, code: str) -> dict[str, Any]:
        for candidate in _codes(code):
            row = products_module.get_product(conn, candidate)
            if row is not None:
                return row
        raise ToolError(
            f"No product with barcode {code} in LabelLens. If you only know its name, "
            "call search_products and use the barcode it returns."
        )

    @tool(
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
        if not rows:
            raise ToolError(
                f"No products match {query!r}. Try fewer words, the brand, or the barcode."
            )
        results = [listed(r) for r in rows]
        output = SearchOutput(query=query, results=results, source=source())
        lines = [f"{len(results)} products matching {query!r}, best known first:"]
        lines += [
            f"{i}. {text.named(p)}, barcode {p.code}, {text.grade(p.nutriscore_grade)}. {p.url}"
            for i, p in enumerate(results, 1)
        ]
        return _result("\n".join([*lines, "", text.attribution(output.source)]), output)

    @apps.tool(
        resource_uri=CARD_URI,
        title="Get product label",
        description=(
            "The label of one product by barcode: Nutri-Score, NOVA processing group, "
            "nutrients per 100 g and additives (with the ones Open Food Facts flags for a high "
            "overexposure risk). Call search_products first if you only have a name. For "
            "healthier alternatives or something to eat instead, use find_swaps."
        ),
        annotations=READ_ONLY,
    )
    def get_product(code: Barcode) -> Annotated[CallToolResult, ProductOutput]:
        with _connection(get_db()) as conn:
            row = product_row(conn, code)
            ids = [a["additive_id"] for a in row["additives"]]
            flagged = additives_module.flagged_ids(conn, ids)
        product = CardProduct(
            **listed(row).model_dump(),
            category_name=row["category_name"],
            nutrition=Nutrition(**row["nutrition"]),
            additives=[
                CardAdditive(
                    additive_id=a["additive_id"],
                    e_number=a["e_number"],
                    name=a["name"],
                    function=a["function"],
                    flagged=a["additive_id"] in flagged,
                )
                for a in row["additives"]
            ],
            off_url=row["off_url"],
        )
        output = ProductOutput(product=product, source=source())
        return _result(text.product_text(product, output.source), output)

    @apps.tool(
        resource_uri=CARD_URI,
        title="Find better swaps",
        description=(
            "Healthier alternatives to one product, by barcode: similar products in the same "
            "category with a better Nutri-Score and no additive flagged by Open Food Facts, "
            "each with the reason it is better. Use it whenever someone wants something "
            "better, healthier or to eat instead. It already returns the product's own name "
            "and Nutri-Score, so get_product is not needed first. Call search_products first "
            "if you only have a name."
        ),
        annotations=READ_ONLY,
    )
    def find_swaps(
        code: Barcode,
        limit: Annotated[int, Field(ge=1, le=10, description="How many swaps, 1 to 10.")] = 5,
    ) -> Annotated[CallToolResult, SwapsOutput]:
        with _connection(get_db()) as conn:
            row = product_row(conn, code)
            swaps = swaps_module.find_swaps(conn, row["code"], limit) or []
        output = SwapsOutput(
            product=listed(row),
            swaps=[
                CardSwap(
                    product=listed(s["product"]),
                    reason=s["reason"],
                    additive_count=s["additive_count"],
                )
                for s in swaps
            ],
            source=source(),
        )
        return _result(text.swaps_text(output), output)

    @tool(
        title="Explain an additive",
        description=(
            "What a food additive is and what it does, by E-number (E471), Open Food Facts id "
            "(en:e471) or name (carrageenan): its function, a short plain-English explainer, "
            "and whether Open Food Facts flags it for a high overexposure risk."
        ),
        annotations=READ_ONLY,
    )
    def explain_additive(
        additive: Annotated[
            str,
            Field(
                min_length=2,
                max_length=100,
                description="E-number, Open Food Facts id or name, e.g. 'E471' or 'carrageenan'.",
            ),
        ],
    ) -> Annotated[CallToolResult, AdditiveOutput]:
        with _connection(get_db()) as conn:
            row = additives_module.get_additive(conn, additive)
        if row is None:
            raise ToolError(
                f"No additive matches {additive!r}. Try its E-number (like E471) or its full "
                "name (like monosodium glutamate)."
            )
        explainer = (
            Explainer(text=row["explainer"], ai_generated=row["explainer_ai"])
            if row["explainer"]
            else None
        )
        output = AdditiveOutput(
            additive_id=row["additive_id"],
            e_number=row["e_number"],
            name=row["name"],
            function=row["function"],
            explainer=explainer,
            flagged=row["flagged"],
            source=source(),
        )
        return _result(text.additive_text(output), output)

    server = MCPServer(
        "LabelLens", instructions=INSTRUCTIONS, website_url=web_url, extensions=[apps]
    )
    for fn, kwargs in plain:
        server.tool(**kwargs)(fn)

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
    # The SDK's handler, behind the per-client limit, on a route of our own: the methods MCP
    # uses, and out of the generated OpenAPI (docs/openapi.yaml documents /mcp by hand).
    route = Route(
        PATH,
        endpoint=RateLimited(sdk_route.endpoint, per_minute),
        methods=["GET", "POST", "DELETE"],
        include_in_schema=False,
    )
    return McpApp(server, route)


def _connection(db: Database) -> AbstractContextManager[DictConnection]:
    """One pooled connection for one tool call."""
    return contextmanager(db.connection)()
