"""The MCP server: tools in-process over the fixture database, and /mcp over HTTP."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mcp import Client

from api.app.config import Settings
from api.app.db import Database
from api.app.main import create_app
from api.app.mcp.server import McpApp, create_mcp

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
    assert "search_products" in tools
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
