"""The latency runner against a tiny local server with known delays."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from evals.runners import search_latency as latency


class _Search(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        q = parse_qs(urlparse(self.path).query)["q"][0]
        if q == "slow":
            time.sleep(0.05)
        status = 503 if q == "broken" else 200
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b'{"results": []}')


@pytest.fixture
def server() -> Iterator[str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Search)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_percentiles_use_nearest_rank() -> None:
    values = [float(v) for v in range(1, 101)]
    assert latency.percentile(values, 50) == 50
    assert latency.percentile(values, 95) == 95
    assert latency.percentile(values, 99) == 99
    assert latency.percentile([7.0], 95) == 7


def test_dataset_mixes_words_prefixes_and_barcodes() -> None:
    queries = latency.load_queries()
    assert len(queries) >= 50
    assert any(q.isdigit() and len(q) == 13 for q in queries)
    assert any(q.isdigit() and len(q) == 12 for q in queries)
    assert not any(q.startswith("#") for q in queries)


def test_run_reports_against_the_target(server: str) -> None:
    report = latency.run(server, ["fast", "slow"], 20, label="test")
    assert report.requests == 20
    assert report.errors == 0
    assert report.p95_ms >= 50  # half the requests sleep 50 ms
    assert report.slowest[0][0] == "slow"
    assert report.meets_target == (report.p95_ms < 300)


def test_errors_fail_the_target(server: str) -> None:
    report = latency.run(server, ["fast", "broken"], 10, label="test")
    assert report.errors == 5
    assert report.meets_target is False


def test_main_writes_json_and_markdown(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(latency, "load_queries", lambda: ["fast"])
    assert (
        latency.main(
            ["--base-url", server, "--requests", "5", "--label", "t", "--out-dir", str(tmp_path)]
        )
        == 0
    )
    data = json.loads((tmp_path / "search_latency_t.json").read_text("utf-8"))
    assert data["requests"] == 5
    assert "| **p95** |" in (tmp_path / "search_latency_t.md").read_text("utf-8")
