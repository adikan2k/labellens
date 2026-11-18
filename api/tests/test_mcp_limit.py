"""The per-client rate limit on /mcp."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.app.config import Settings
from api.app.main import create_app
from api.app.mcp.limit import WINDOW_SECONDS, RateLimited


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def _app(scope: Any, receive: Any, send: Any) -> None:  # never reached in unit tests
    raise AssertionError


def test_a_client_gets_its_limit_then_a_retry_time() -> None:
    clock = Clock()
    limiter = RateLimited(_app, per_minute=3, clock=clock)
    assert [limiter.check("a") for _ in range(3)] == [None, None, None]
    clock.now += 20
    assert limiter.check("a") == 40  # the first request leaves the window in 40 s
    assert limiter.check("b") is None  # another client is unaffected


def test_the_window_slides() -> None:
    clock = Clock()
    limiter = RateLimited(_app, per_minute=2, clock=clock)
    limiter.check("a")
    clock.now += 30
    limiter.check("a")
    clock.now += WINDOW_SECONDS - 30  # the first has left the window; the second has not
    assert limiter.check("a") is None
    assert limiter.check("a") is not None


def _list_tools(client: TestClient, forwarded: str) -> Any:
    return client.post(
        "/mcp",
        headers={
            "Accept": "application/json, text/event-stream",
            "X-Forwarded-For": forwarded,
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "tools/list",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
        }}},
    )  # fmt: skip


def test_over_http_the_next_request_gets_429_with_retry_after() -> None:
    settings = Settings(_env_file=None, database_url=None, mcp_rate_limit_per_minute=2)  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as client:
        # Cloud Run appends the real address last; a client cannot pick its own.
        me = "203.0.113.9, 198.51.100.7"
        assert [_list_tools(client, me).status_code for _ in range(2)] == [200, 200]
        refused = _list_tools(client, me)
        assert refused.status_code == 429
        assert 1 <= int(refused.headers["retry-after"]) <= 60
        assert refused.json()["error"]["message"].startswith("Too many LabelLens requests")
        assert _list_tools(client, "203.0.113.9, 198.51.100.8").status_code == 200


def test_ipv6_neighbours_share_one_limit() -> None:
    settings = Settings(_env_file=None, database_url=None, mcp_rate_limit_per_minute=1)  # pyright: ignore[reportCallIssue]
    with TestClient(create_app(settings)) as client:
        assert _list_tools(client, "2600:1700:3a70:1380::1").status_code == 200
        # A rotated privacy address in the same /64 is the same client.
        assert _list_tools(client, "2600:1700:3a70:1380:fc79::2").status_code == 429
        assert _list_tools(client, "2600:1700:3a70:1381::1").status_code == 200
