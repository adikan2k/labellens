"""The MCP server: tools in-process over the fixture database, and /mcp over HTTP."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client
from mcp.server.apps import APP_MIME_TYPE
from psycopg.rows import dict_row

from api.app import swaps as swaps_module
from api.app.additives import normalise
from api.app.config import Settings
from api.app.db import Database, DictConnection
from api.app.main import create_app
from api.app.mcp.server import CARD_URI, FONT_HOSTS, McpApp, create_mcp

WEB = "https://labellens.test"
MODERN = "2026-07-28"
ENVELOPE = {
    "io.modelcontextprotocol/protocolVersion": MODERN,
    "io.modelcontextprotocol/clientCapabilities": {},
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def db(serving_url: str) -> Iterator[Database]:
    database = Database.open(serving_url, timeout=5)
    yield database
    database.close()


@pytest.fixture
def mcp(db: Database) -> McpApp:
    return create_mcp(lambda: db, WEB)


@pytest.fixture
async def client(mcp: McpApp) -> AsyncIterator[Client]:
    async with Client(mcp.server, raise_exceptions=True) as c:
        yield c


def text(result: Any) -> str:
    return "\n".join(block.text for block in result.content)


@pytest.mark.anyio
async def test_the_tools_are_listed_read_only(client: Client) -> None:
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"search_products", "get_product", "find_swaps", "explain_additive"}
    for tool in tools.values():
        assert tool.annotations and tool.annotations.read_only_hint, tool.name
        assert tool.output_schema, tool.name
        assert tool.description and len(tool.description) > 60, tool.name


@pytest.mark.anyio
async def test_search_returns_text_and_structured_results(client: Client) -> None:
    result = await client.call_tool("search_products", {"query": "cereal", "limit": 3})
    assert not result.is_error
    data = result.structured_content
    assert data and data["query"] == "cereal" and 1 <= len(data["results"]) <= 3
    first = data["results"][0]
    assert first["url"] == f"{WEB}/product/{first['code']}"
    body = text(result)
    assert f"barcode {first['code']}" in body and first["url"] in body
    assert body.endswith("snapshot of November 17, 2026.")
    assert "Open Database License" in body


@pytest.mark.anyio
async def test_no_match_is_a_tool_error_with_a_next_step(client: Client) -> None:
    result = await client.call_tool("search_products", {"query": "zzqqxx"})
    assert result.is_error and "Try fewer words" in text(result)


@pytest.fixture(scope="module")
def picks(serving_url: str) -> dict[str, Any]:
    """Fixture rows the tool tests need, chosen by query like the API tests do."""
    with DictConnection.connect(serving_url, row_factory=dict_row) as pg:
        flagged = pg.execute(
            "select p.code, a.additive_id, a.e_number, a.name from serving.products p "
            "join serving.additives a on a.additive_id = any(p.additive_ids) "
            "where a.flagged and a.e_number is not null and p.name is not null "
            "order by p.rank_pos limit 1"
        ).fetchone()
        explained = pg.execute(
            "select additive_id, e_number, name, explainer from serving.additives "
            "where explainer is not null and e_number is not null order by additive_id limit 1"
        ).fetchone()
        candidates = pg.execute(
            "select code from serving.products where nutriscore_grade in ('d', 'e') "
            "order by rank_pos limit 200"
        ).fetchall()
        with_swaps = next(
            (c["code"] for c in candidates if swaps_module.find_swaps(pg, c["code"], 3)),
            None,
        )
    if not (flagged and explained and with_swaps):
        pytest.skip("fixture lacks a flagged additive, an explainer or a product with swaps")
    return {"flagged": flagged, "explained": explained, "with_swaps": with_swaps}


@pytest.mark.anyio
async def test_get_product_gives_the_label_and_marks_flagged_additives(
    client: Client, picks: dict[str, Any]
) -> None:
    flagged = picks["flagged"]
    result = await client.call_tool("get_product", {"code": flagged["code"]})
    assert not result.is_error, text(result)
    data = result.structured_content
    assert data and data["view"] == "product"
    product = data["product"]
    assert product["code"] == flagged["code"] and product["url"].endswith(flagged["code"])
    assert set(product["nutrition"]) >= {"energy_kcal_100g", "sugars_100g", "salt_100g"}
    marked = {a["additive_id"]: a["flagged"] for a in product["additives"]}
    assert marked[flagged["additive_id"]] is True
    body = text(result)
    assert f"barcode {flagged['code']}" in body and "Per 100 g:" in body
    assert f"{flagged['e_number']}: flagged by Open Food Facts" in body
    assert "ingredients" not in product  # the card shows the label, not the full ingredient list


@pytest.mark.anyio
async def test_a_12_digit_upc_finds_the_stored_ean(client: Client, picks: dict[str, Any]) -> None:
    code = picks["flagged"]["code"]
    if not (len(code) == 13 and code.startswith("0")):
        pytest.skip("picked product is not a zero-led EAN-13")
    result = await client.call_tool("get_product", {"code": code[1:]})
    assert not result.is_error and result.structured_content["product"]["code"] == code  # type: ignore[index]


@pytest.mark.anyio
async def test_unknown_barcode_points_to_search(client: Client) -> None:
    result = await client.call_tool("get_product", {"code": "0000000000000"})
    assert result.is_error and "call search_products" in text(result)


@pytest.mark.anyio
async def test_find_swaps_lists_better_products_with_reasons(
    client: Client, picks: dict[str, Any]
) -> None:
    result = await client.call_tool("find_swaps", {"code": picks["with_swaps"], "limit": 3})
    assert not result.is_error, text(result)
    data = result.structured_content
    assert data and data["view"] == "swaps" and data["product"]["code"] == picks["with_swaps"]
    assert 1 <= len(data["swaps"]) <= 3
    for swap in data["swaps"]:
        assert swap["reason"] and swap["product"]["url"].startswith(f"{WEB}/product/")
    assert "better swaps in the same category" in text(result)


@pytest.mark.anyio
@pytest.mark.parametrize("form", ["e_number", "lower", "spaced", "id", "name"])
async def test_explain_additive_by_any_name(
    client: Client, picks: dict[str, Any], form: str
) -> None:
    row = picks["explained"]
    term = {
        "e_number": row["e_number"],
        "lower": row["e_number"].lower(),
        "spaced": f"E {row['e_number'][1:]}",
        "id": row["additive_id"],
        "name": row["name"].upper(),
    }[form]
    result = await client.call_tool("explain_additive", {"additive": term})
    assert not result.is_error, text(result)
    data = result.structured_content
    assert data and data["additive_id"] == row["additive_id"]
    assert data["explainer"]["text"] == row["explainer"]
    assert "written by AI" in text(result)


def test_an_e_number_without_its_suffix_finds_its_family() -> None:
    assert normalise("E322")["prefix"] == "e322%"  # type: ignore[index]  # stored as E322i
    assert normalise("e 150 a")["id"] == "en:e150a"  # type: ignore[index]
    assert normalise("E322(i)")["e"] == "e322i"  # type: ignore[index]
    assert "prefix" not in normalise("carrageenan")  # type: ignore[operator]
    assert normalise("   ") is None
    assert normalise(" MSG ")["id"] == "en:e621"  # type: ignore[index]  # label abbreviations


@pytest.mark.anyio
async def test_unknown_additive_suggests_what_to_try(client: Client) -> None:
    result = await client.call_tool("explain_additive", {"additive": "zzqqxx"})
    assert result.is_error and "E-number" in text(result)


# --- The card (MCP Apps) -------------------------------------------------------------------

CARD = (Path(__file__).parents[1] / "app" / "mcp" / "card.html").read_text("utf-8")
DESIGN = (Path(__file__).parents[2] / "docs" / "DESIGN.md").read_text("utf-8")


@pytest.mark.anyio
async def test_label_tools_link_the_card_and_text_tools_do_not(client: Client) -> None:
    tools = {t.name: t for t in (await client.list_tools()).tools}
    for name in ("get_product", "find_swaps"):
        assert (tools[name].meta or {}).get("ui") == {"resourceUri": CARD_URI}, name
    for name in ("search_products", "explain_additive"):
        assert "ui" not in (tools[name].meta or {}), name


@pytest.mark.anyio
async def test_the_card_is_an_mcp_app_resource_that_loads_only_fonts(client: Client) -> None:
    listed = {str(r.uri): r for r in (await client.list_resources()).resources}
    card = listed[CARD_URI]
    assert card.mime_type == APP_MIME_TYPE
    ui = (card.meta or {})["ui"]
    assert ui["csp"] == {"resourceDomains": FONT_HOSTS} and ui["prefersBorder"] is False
    read = await client.read_resource(CARD_URI)
    html = read.contents[0].text  # type: ignore[union-attr]
    assert "ui/initialize" in html and "ui/notifications/tool-result" in html


def test_the_card_uses_only_design_tokens() -> None:
    tokens = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", DESIGN)}
    used = {c.upper() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", CARD)}
    assert used and used <= tokens, used - tokens


def test_the_card_reaches_no_host_beyond_fonts_and_attribution() -> None:
    hosts = set(re.findall(r"https://([a-z0-9.-]+)", CARD))
    assert hosts == {"fonts.googleapis.com", "fonts.gstatic.com",
                     "world.openfoodfacts.org", "opendatacommons.org"}  # fmt: skip
    # Product names are data: the card builds text nodes, never markup.
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in CARD, sink


def test_the_card_carries_the_odbl_attribution_and_reduced_motion() -> None:
    assert "Contains data from " in CARD and "Open Database License" in CARD
    assert "prefers-reduced-motion: no-preference" in CARD  # motion only when allowed


# --- Over HTTP -----------------------------------------------------------------------------


def _post(client: TestClient, method: str, params: dict[str, Any], **headers: str) -> Any:
    return client.post(
        "/mcp",
        headers={"Accept": "application/json, text/event-stream", **headers},
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )


@pytest.fixture(scope="module")
def http(serving_url: str) -> Iterator[TestClient]:
    settings = Settings(_env_file=None, database_url=serving_url, public_web_url=WEB)  # pyright: ignore[reportCallIssue]
    app = create_app(settings)
    with TestClient(app) as c:
        yield c


def test_post_mcp_answers_a_stateless_2026_client(http: TestClient) -> None:
    headers = {"MCP-Protocol-Version": MODERN, "Mcp-Method": "tools/list"}
    response = _post(http, "tools/list", {"_meta": ENVELOPE}, **headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/json")
    names = {t["name"] for t in response.json()["result"]["tools"]}
    assert "search_products" in names
    assert "mcp-session-id" not in response.headers  # sessionless: any instance can answer


def test_an_older_client_needs_no_session_either(http: TestClient) -> None:
    init = _post(http, "initialize", {
        "protocolVersion": "2025-11-25", "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    })  # fmt: skip
    assert init.status_code == 200, init.text
    # A follow-up without the session id works: stateless_http, so no sticky routing.
    listed = _post(http, "tools/list", {}, **{"MCP-Protocol-Version": "2025-11-25"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["result"]["tools"]


def test_mcp_lives_at_exactly_one_path(http: TestClient) -> None:
    other = http.get("/nope")
    assert other.status_code == 404 and "source" in other.json()  # the API's own JSON error
