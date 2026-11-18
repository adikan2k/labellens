"""The smoke test against a local stub of the API and the web app."""

from __future__ import annotations

import io
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from scripts import smoke

CODE = smoke.CODE
SOURCE = {"name": "Open Food Facts", "snapshot_date": "2026-11-17"}
PRODUCT = {"code": CODE, "name": "Lucky Charms", "nutriscore_grade": "d"}
GET: dict[str, Any] = {
    "/health": {"status": "ok", "versions": {"api": "0.3.0"}, "source": SOURCE},
    "/search": {"query": "cheerios", "results": [{"code": "1", "name": "Cheerios"}]},
    f"/products/{CODE}": {"product": PRODUCT, "source": SOURCE},
    f"/products/{CODE}/swaps": {"code": CODE, "swaps": [{"product": PRODUCT}]},
    "/graph/neighborhood": {
        "center": f"Product:{CODE}",
        "nodes": [{"id": f"Product:{CODE}"}, {"id": "Brand:x"}],
        "edges": [{"source": f"Product:{CODE}", "target": "Brand:x"}],
    },
}
PAGE = b"<html><footer>Contains data from Open Food Facts (ODbL)</footer></html>"


class Stub:
    """Canned answers; tests break one path at a time and read what was requested."""

    def __init__(self) -> None:
        self.overrides: dict[str, tuple[int, Any]] = {}
        self.requests: list[tuple[str, str, dict[str, str], Any]] = []
        self.unknown_status = 404


def _handler(stub: Stub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            pass

        def _send(self, status: int, body: Any) -> None:
            raw = body if isinstance(body, bytes) else json.dumps(body).encode()
            kind = "text/html" if isinstance(body, bytes) else "application/json"
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self) -> None:
            path = self.path.split("?")[0]
            stub.requests.append(("GET", self.path, dict(self.headers), None))
            if path in stub.overrides:
                return self._send(*stub.overrides[path])
            if path in GET:
                return self._send(200, GET[path])
            if path == f"/web/product/{smoke.UNKNOWN}":
                return self._send(stub.unknown_status, PAGE)
            if path.startswith("/web"):
                return self._send(200, PAGE)
            self._send(404, {"detail": "nope"})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"null")
            stub.requests.append(("POST", self.path, dict(self.headers), body))
            if self.path in stub.overrides:
                return self._send(*stub.overrides[self.path])
            if self.path == "/ask":
                status = 422 if len(body["question"]) < 3 else 500  # a model call fails the test
                return self._send(status, {"detail": "too short"})
            if self.path == "/mcp":
                if body["method"] == "tools/list":
                    tools = [{"name": n} for n in sorted(smoke.MCP_TOOLS)]
                    return self._send(200, {"jsonrpc": "2.0", "id": 1, "result": {"tools": tools}})
                result = {"isError": False, "structuredContent": {"product": PRODUCT}}
                return self._send(200, {"jsonrpc": "2.0", "id": 1, "result": result})
            self._send(404, {"detail": "nope"})

    return Handler


@pytest.fixture
def stub() -> Iterator[tuple[Stub, str]]:
    state = Stub()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _run(base: str, **kwargs: Any) -> tuple[list[smoke.Result], str]:
    out = io.StringIO()
    results = smoke.run(base, f"{base}/web/", out=out, timeout=5, **kwargs)
    return results, out.getvalue()


def test_a_healthy_deployment_passes_every_check(stub: tuple[Stub, str]) -> None:
    _, base = stub
    results, printed = _run(base)
    assert all(r.ok for r in results), printed
    assert len(results) == 8 + len(smoke.PAGES)
    assert len(printed.splitlines()) == len(results) + 1  # one line per check, then a total
    assert printed.rstrip().endswith(f"{len(results)}/{len(results)} checks passed.")


def test_requests_are_read_only_and_ask_calls_no_model(stub: tuple[Stub, str]) -> None:
    state, base = stub
    _run(base)
    posts = [(path, body) for method, path, _, body in state.requests if method == "POST"]
    assert {path for path, _ in posts} == {"/ask", "/mcp"}
    asked = [body["question"] for path, body in posts if path == "/ask"]
    assert asked == ["hi"]  # under the 3-character minimum: rejected before the model
    calls = [body["params"]["name"] for path, body in posts if body.get("method") == "tools/call"]
    assert calls == ["get_product"]


def test_mcp_requests_carry_the_2026_headers_and_meta(stub: tuple[Stub, str]) -> None:
    state, base = stub
    _run(base)
    mcp = [(headers, body) for _, path, headers, body in state.requests if path == "/mcp"]
    assert [body["method"] for _, body in mcp] == ["tools/list", "tools/call"]
    for headers, body in mcp:
        assert headers["MCP-Protocol-Version"] == "2026-07-28"
        assert headers["Mcp-Method"] == body["method"]
        meta = body["params"]["_meta"]
        assert meta["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
        assert "io.modelcontextprotocol/clientCapabilities" in meta
    assert mcp[1][0]["Mcp-Name"] == "get_product"


@pytest.mark.parametrize(
    ("path", "answer", "check", "reason"),
    [
        ("/health", (503, {"detail": "down"}), "api /health", "HTTP 503"),
        ("/search", (200, {"results": []}), "api /search?q=cheerios", "no results"),
        ("/graph/neighborhood", (200, {"center": "x"}), "api /graph/neighborhood", "center"),
        ("/ask", (200, {}), "api POST /ask (too short)", "expected 422"),
        ("/mcp", (200, {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}), "mcp tools/list",
         "tools are"),
        ("/web/about", (500, b"oops"), "web /about", "HTTP 500"),
        ("/web/", (200, b"<html>no attribution</html>"), "web /", "attribution"),
    ],
)  # fmt: skip
def test_a_broken_endpoint_fails_its_check(
    stub: tuple[Stub, str], path: str, answer: tuple[int, Any], check: str, reason: str
) -> None:
    state, base = stub
    state.overrides[path] = answer
    results, printed = _run(base)
    failed = [r for r in results if not r.ok]
    assert check in {r.name for r in failed}, printed
    assert any(reason in r.detail for r in failed), printed
    assert f"FAIL {check}" in printed


def test_unknown_product_404_is_checked_only_behind_the_flag(stub: tuple[Stub, str]) -> None:
    state, base = stub
    state.unknown_status = 200  # today's behaviour, until the web fix ships
    results, _ = _run(base)
    assert all(r.ok for r in results)
    results, _ = _run(base, expect_unknown_404=True)
    assert [r.name for r in results if not r.ok] == [f"web /product/{smoke.UNKNOWN} (unknown)"]
    state.unknown_status = 404
    results, _ = _run(base, expect_unknown_404=True)
    assert all(r.ok for r in results)


def test_main_exits_non_zero_on_failure(
    stub: tuple[Stub, str], capsys: pytest.CaptureFixture[str]
) -> None:
    state, base = stub
    assert smoke.main(["--api", base, "--web", f"{base}/web"]) == 0
    state.overrides["/health"] = (500, {"detail": "boom"})
    assert smoke.main(["--api", base, "--web", f"{base}/web"]) == 1
    assert "FAIL api /health" in capsys.readouterr().out


def test_an_unreachable_host_fails_instead_of_crashing() -> None:
    out = io.StringIO()
    results = smoke.run("http://127.0.0.1:9", "http://127.0.0.1:9", out=out, timeout=0.2)
    assert results and not any(r.ok for r in results)
    assert "Connect" in out.getvalue()  # ConnectError, or ConnectTimeout on Windows
