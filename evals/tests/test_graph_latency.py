"""The graph latency runner against a tiny local server standing in for the API."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from evals.runners import graph_latency as latency

IN_GRAPH = {"001", "002"}


class _Api(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def _send(self, body: dict, status: int = 200) -> None:
        self.send_response(status)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/search":
            self._send({"results": [{"code": c} for c in ("001", "002", "003")]})
        elif url.path.startswith("/products/") and url.path.endswith("/swaps"):
            self._send({"swaps": []})
        elif url.path.startswith("/products/"):
            code = url.path.rsplit("/", 1)[1]
            self._send({"product": {"code": code, "in_graph": code in IN_GRAPH}})
        elif url.path == "/graph/neighborhood":
            code = parse_qs(url.query)["code"][0]
            self._send({"center": code}, 200 if code in IN_GRAPH else 404)
        else:
            self._send({}, 404)


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Api)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_only_products_the_graph_holds_are_timed(server: str) -> None:
    assert latency.graph_products(server, 10) == ["001", "002"]


def test_report_has_both_endpoints_against_the_target(server: str, tmp_path: Path) -> None:
    assert latency.main(["--base-url", server, "--products", "5", "--label", "t",
                         "--out-dir", str(tmp_path)]) == 0  # fmt: skip
    data = json.loads((tmp_path / "graph_latency_t.json").read_text("utf-8"))
    assert data["products"] == 2
    assert [t["endpoint"] for t in data["timings"]] == [
        "/graph/neighborhood?depth=2",
        "/products/{code}/swaps",
    ]
    assert all(t["errors"] == 0 and t["meets_target"] for t in data["timings"])
    assert "| 1 s target |" in (tmp_path / "graph_latency_t.md").read_text("utf-8")
