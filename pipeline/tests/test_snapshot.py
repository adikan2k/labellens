"""Snapshot tests against a small local HTTP server that mimics Hugging Face.

The server answers HEAD /resolve/main/... with a 302 carrying X-Repo-Commit and X-Linked-Size,
and serves GET /resolve/<commit>/... with Range support, so resume is exercised for real.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Iterator
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from pipeline.ingest import snapshot as snap

PAYLOAD = bytes(range(256)) * 400  # 102,400 bytes
COMMIT = "abc123def4567890"
TAXONOMY = json.dumps({"en:e330": {"name": {"en": "Citric acid"}}}).encode()


class _Handler(BaseHTTPRequestHandler):
    ignore_range = False
    requests: list[tuple[str, str, str | None]] = []  # noqa: RUF012

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_HEAD(self) -> None:
        self.requests.append(("HEAD", self.path, None))
        if self.path.endswith("additives.json"):  # static host: plain 200, no commit
            self.send_response(200)
            self.send_header("Content-Length", str(len(TAXONOMY)))
            self.send_header("ETag", '"static-etag"')
            self.end_headers()
            return
        self.send_response(302)
        self.send_header("Location", f"/resolve/{COMMIT}/food.parquet")
        self.send_header("X-Repo-Commit", COMMIT)
        self.send_header("X-Linked-Size", str(len(PAYLOAD)))
        self.send_header("X-Linked-ETag", f'"{hashlib.sha256(PAYLOAD).hexdigest()}"')
        self.end_headers()

    def do_GET(self) -> None:
        range_header = self.headers.get("Range")
        self.requests.append(("GET", self.path, range_header))
        if self.path.endswith("additives.json"):
            self.send_response(200)
            self.send_header("Content-Length", str(len(TAXONOMY)))
            self.end_headers()
            self.wfile.write(TAXONOMY)
            return
        start = 0
        if range_header and not self.ignore_range:
            start = int(range_header.removeprefix("bytes=").split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        else:
            self.send_response(200)
        body = PAYLOAD[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server() -> Iterator[str]:
    _Handler.requests = []
    _Handler.ignore_range = False
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/resolve/main/food.parquet"
    httpd.shutdown()


def _make_writable(path: Path) -> None:
    os.chmod(path, 0o644)  # let tmp_path cleanup delete the read-only snapshot


def test_fetch_metadata_reads_302_headers_and_pins_commit(server: str) -> None:
    remote = snap.fetch_metadata(server)

    assert remote.commit == COMMIT
    assert remote.size == len(PAYLOAD)
    assert remote.url.endswith(f"/resolve/{COMMIT}/food.parquet")
    assert remote.etag == hashlib.sha256(PAYLOAD).hexdigest()


def test_snapshot_downloads_writes_manifest_and_locks_file(server: str, tmp_path: Path) -> None:
    path = snap.snapshot(tmp_path, date(2026, 11, 17), url=server)

    assert path == tmp_path / "2026-11-17" / "food.parquet"
    assert path.read_bytes() == PAYLOAD
    assert not os.access(path, os.W_OK)
    manifest = json.loads((path.parent / "manifest.json").read_text("utf-8"))
    assert manifest["dataset_commit"] == COMMIT
    assert manifest["bytes"] == len(PAYLOAD)
    assert manifest["sha256"] == hashlib.sha256(PAYLOAD).hexdigest()
    assert manifest["sha256_matches_remote_etag"] is True
    assert not list(path.parent.glob("*.part"))
    _make_writable(path)


def test_snapshot_resumes_from_partial_file(server: str, tmp_path: Path) -> None:
    part = tmp_path / "2026-11-17" / f"food.parquet.{COMMIT[:12]}.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(PAYLOAD[:40_000])

    path = snap.snapshot(tmp_path, date(2026, 11, 17), url=server)

    assert path.read_bytes() == PAYLOAD
    gets = [r for r in _Handler.requests if r[0] == "GET"]
    assert gets == [("GET", f"/resolve/{COMMIT}/food.parquet", "bytes=40000-")]
    _make_writable(path)


def test_snapshot_restarts_when_server_ignores_range(server: str, tmp_path: Path) -> None:
    _Handler.ignore_range = True
    part = tmp_path / "2026-11-17" / f"food.parquet.{COMMIT[:12]}.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"x" * 1000)

    path = snap.snapshot(tmp_path, date(2026, 11, 17), url=server)

    assert path.read_bytes() == PAYLOAD
    _make_writable(path)


def test_snapshot_refuses_to_overwrite(server: str, tmp_path: Path) -> None:
    existing = tmp_path / "2026-11-17" / "food.parquet"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(b"old")

    with pytest.raises(snap.SnapshotExistsError):
        snap.snapshot(tmp_path, date(2026, 11, 17), url=server)

    assert existing.read_bytes() == b"old"
    assert _Handler.requests == []


def _taxonomy_url(server: str) -> str:
    return server.split("/resolve/")[0] + "/data/taxonomies/additives.json"


def test_taxonomy_is_added_beside_the_parquet_without_touching_it(
    server: str, tmp_path: Path
) -> None:
    folder = tmp_path / "2026-11-17"
    folder.mkdir()
    (folder / "manifest.json").write_text('{"keep": "me"}', "utf-8")

    path = snap.snapshot_taxonomy(folder, url=_taxonomy_url(server))

    assert path.read_bytes() == TAXONOMY
    assert not os.access(path, os.W_OK)
    assert (folder / "manifest.json").read_text("utf-8") == '{"keep": "me"}'
    manifest = json.loads((folder / "additives.manifest.json").read_text("utf-8"))
    assert manifest["bytes"] == len(TAXONOMY)
    assert manifest["sha256"] == hashlib.sha256(TAXONOMY).hexdigest()
    assert manifest["remote_etag"] == "static-etag"
    assert not list(folder.glob("*.part"))
    _make_writable(path)


def test_taxonomy_refuses_to_overwrite(server: str, tmp_path: Path) -> None:
    (tmp_path / "additives.json").write_bytes(b"old")

    with pytest.raises(snap.SnapshotExistsError):
        snap.snapshot_taxonomy(tmp_path, url=_taxonomy_url(server))

    assert (tmp_path / "additives.json").read_bytes() == b"old"


def test_taxonomy_only_needs_an_existing_snapshot(tmp_path: Path) -> None:
    code = snap.main(["--data-dir", str(tmp_path), "--date", "2026-11-17", "--taxonomy-only"])
    assert code == 1


def test_taxonomy_only_adds_to_existing_snapshot(
    server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(snap, "ADDITIVES_URL", _taxonomy_url(server))
    folder = tmp_path / "2026-11-17"
    folder.mkdir()
    (folder / "food.parquet").write_bytes(b"parquet")

    code = snap.main(["--data-dir", str(tmp_path), "--date", "2026-11-17", "--taxonomy-only"])

    assert code == 0
    assert (folder / "food.parquet").read_bytes() == b"parquet"
    assert (folder / "additives.json").read_bytes() == TAXONOMY
    assert [r for r in _Handler.requests if "food.parquet" in r[1]] == []
    _make_writable(folder / "additives.json")
