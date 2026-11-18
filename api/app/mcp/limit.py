"""A per-client rate limit for /mcp, held in memory.

A client is an IPv4 address or an IPv6 /64 (api/app/ask/service.py `client_key`), from the last
X-Forwarded-For entry Cloud Run appends. A sliding window of `per_minute` requests.

In memory, not in Postgres like /ask: every MCP tool is a cheap read of the serving tables, so a
database write per call would cost more than the abuse it stops. With at most two Cloud Run
instances, the effective ceiling is twice the setting (decision 0008).
"""

from __future__ import annotations

import json
import math
import time
from collections import deque
from collections.abc import Callable

from starlette.types import ASGIApp, Receive, Scope, Send

from api.app.ask.service import client_address, client_key

WINDOW_SECONDS = 60.0
MAX_CLIENTS = 50_000  # past this, idle clients are forgotten first


class RateLimited:
    """ASGI wrapper: answers 429 with Retry-After once a client is over the limit."""

    def __init__(
        self,
        app: ASGIApp,
        per_minute: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.app = app
        self.per_minute = per_minute
        self.clock = clock
        self.hits: dict[str, deque[float]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        retry = self.check(self._client(scope))
        if retry is None:
            await self.app(scope, receive, send)
            return
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": None,
            "error": {
                "code": -32000,
                "message": f"Too many LabelLens requests from here. Try again in {retry} s.",
            },
        }).encode()  # fmt: skip
        await send({
            "type": "http.response.start",
            "status": 429,
            "headers": [
                (b"content-type", b"application/json"),
                (b"retry-after", str(retry).encode()),
            ],
        })  # fmt: skip
        await send({"type": "http.response.body", "body": body})

    def check(self, client: str) -> int | None:
        """Count one request. None when allowed, else the seconds until the next one is."""
        now = self.clock()
        hits = self.hits.get(client)
        if hits is None:
            if len(self.hits) >= MAX_CLIENTS:
                self._forget_idle(now)
            hits = self.hits[client] = deque()
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= self.per_minute:
            return max(1, math.ceil(WINDOW_SECONDS - (now - hits[0])))
        hits.append(now)
        return None

    def _forget_idle(self, now: float) -> None:
        for key in [k for k, v in self.hits.items() if not v or now - v[-1] >= WINDOW_SECONDS]:
            del self.hits[key]

    @staticmethod
    def _client(scope: Scope) -> str:
        headers = dict(scope.get("headers") or [])
        forwarded = headers.get(b"x-forwarded-for")
        peer = scope.get("client")
        address = client_address(
            forwarded.decode("latin-1") if forwarded else None, peer[0] if peer else None
        )
        return client_key(address)
