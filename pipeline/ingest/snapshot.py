"""Snapshot food.parquet from Hugging Face into data/raw/<date>/.

Streams to a `.part` file and resumes with HTTP Range requests, so an interrupted 8 GB download
picks up where it stopped. The download is pinned to the dataset commit seen on the first request,
so a resume never stitches two revisions together. A finished snapshot is made read-only and is
never overwritten.

    uv run python -m pipeline.ingest.snapshot [--date YYYY-MM-DD] [--data-dir data/raw]
    uv run python -m pipeline.ingest.snapshot --date 2026-11-17 --taxonomy-only

Each run also saves Open Food Facts' additives taxonomy (additives.json, under 1 MB) beside
the Parquet, with its own additives.manifest.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError

DEFAULT_URL = (
    "https://huggingface.co/datasets/openfoodfacts/product-database/resolve/main/food.parquet"
)
FILE_NAME = "food.parquet"
# Static taxonomy export (not the live API): gives additive names and facts.
ADDITIVES_URL = "https://static.openfoodfacts.org/data/taxonomies/additives.json"
ADDITIVES_FILE = "additives.json"
CHUNK_SIZE = 1024 * 1024
PROGRESS_EVERY = 512 * 1024 * 1024


class SnapshotExistsError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteFile:
    url: str
    size: int
    commit: str | None
    etag: str | None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


def fetch_metadata(url: str) -> RemoteFile:
    """HEAD the URL without following redirects; Hugging Face puts commit and size on the 302."""
    opener = urllib.request.build_opener(_NoRedirect)
    request = urllib.request.Request(url, method="HEAD")
    try:
        response = opener.open(request, timeout=60)
        headers = response.headers
    except HTTPError as error:
        if error.code not in (301, 302, 303, 307, 308):
            raise
        headers = error.headers

    commit = headers.get("X-Repo-Commit")
    size_header = headers.get("X-Linked-Size") or headers.get("Content-Length")
    if size_header is None:
        raise RuntimeError(f"No size reported for {url}")
    etag = (headers.get("X-Linked-ETag") or headers.get("ETag") or "").strip('"') or None

    pinned = url.replace("/resolve/main/", f"/resolve/{commit}/") if commit else url
    return RemoteFile(url=pinned, size=int(size_header), commit=commit, etag=etag)


def download(
    url: str,
    part_path: Path,
    expected_size: int,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> None:
    """Download `url` into `part_path`, resuming from whatever is already there."""
    part_path.parent.mkdir(parents=True, exist_ok=True)
    have = part_path.stat().st_size if part_path.exists() else 0
    if have > expected_size:
        part_path.unlink()
        have = 0
    if have == expected_size:
        return

    headers: dict[str, str] = {}
    if have:
        headers["Range"] = f"bytes={have}-"
    request = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(request, timeout=120) as response:
        if have and response.status != 206:
            have = 0  # server ignored the range; start again
        mode = "ab" if have else "wb"
        next_report = have + PROGRESS_EVERY
        with part_path.open(mode) as out:
            while chunk := response.read(CHUNK_SIZE):
                out.write(chunk)
                have += len(chunk)
                if progress and have >= next_report:
                    progress(have, expected_size)
                    next_report += PROGRESS_EVERY

    if have != expected_size:
        raise RuntimeError(
            f"Download stopped at {have:,} of {expected_size:,} bytes. Run again to resume."
        )


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE * 8):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(
    data_dir: Path,
    snapshot_date: date,
    *,
    url: str = DEFAULT_URL,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    target_dir = data_dir / snapshot_date.isoformat()
    target = target_dir / FILE_NAME
    if target.exists():
        raise SnapshotExistsError(f"{target} already exists; snapshots are never overwritten.")

    remote = fetch_metadata(url)
    tag = (remote.commit or "nocommit")[:12]
    part = target_dir / f"{FILE_NAME}.{tag}.part"

    download(remote.url, part, remote.size, progress=progress)

    digest = sha256_of(part)
    part.rename(target)
    os.chmod(target, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    manifest = {
        "source_url": url,
        "pinned_url": remote.url,
        "dataset_commit": remote.commit,
        "bytes": remote.size,
        "sha256": digest,
        "remote_etag": remote.etag,
        "sha256_matches_remote_etag": remote.etag == digest if remote.etag else None,
        "snapshot_date": snapshot_date.isoformat(),
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (target_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    return target


def snapshot_taxonomy(target_dir: Path, *, url: str | None = None) -> Path:
    """Add Open Food Facts' additives taxonomy to a snapshot folder.

    Writes additives.json and its own additives.manifest.json; never touches existing files.
    """
    url = url or ADDITIVES_URL
    target = target_dir / ADDITIVES_FILE
    if target.exists():
        raise SnapshotExistsError(f"{target} already exists; snapshots are never overwritten.")

    remote = fetch_metadata(url)
    part = target_dir / f"{ADDITIVES_FILE}.part"
    download(remote.url, part, remote.size)
    digest = sha256_of(part)
    part.rename(target)
    os.chmod(target, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)

    manifest = {
        "source_url": url,
        "bytes": remote.size,
        "sha256": digest,
        "remote_etag": remote.etag,
        "downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (target_dir / "additives.manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", "utf-8"
    )
    return target


def _print_progress(have: int, total: int) -> None:
    print(f"  {have / 1e9:5.2f} / {total / 1e9:.2f} GB ({have / total:.0%})", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument(
        "--taxonomy-only",
        action="store_true",
        help="add additives.json to an existing snapshot folder without touching the Parquet",
    )
    args = parser.parse_args(argv)
    target_dir = args.data_dir / args.date.isoformat()

    try:
        if not args.taxonomy_only:
            path = snapshot(args.data_dir, args.date, url=args.url, progress=_print_progress)
            manifest = json.loads((path.parent / "manifest.json").read_text("utf-8"))
            print(f"Snapshot written: {path}")
            print(json.dumps(manifest, indent=2))
            if manifest["sha256_matches_remote_etag"] is False:
                print("Note: SHA-256 differs from the remote ETag; check before relying on it.")
        elif not (target_dir / FILE_NAME).exists():
            print(f"No snapshot in {target_dir}; --taxonomy-only adds to one.", file=sys.stderr)
            return 1
        taxonomy = snapshot_taxonomy(target_dir)
    except SnapshotExistsError as error:
        print(error, file=sys.stderr)
        return 1
    print(f"Taxonomy written: {taxonomy}")
    print((target_dir / "additives.manifest.json").read_text("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
