"""Record the /label page's sample labels: each sample's photos through POST /label, saved.

    uv run python -m scripts.record_label_samples          # prints the estimate, sends nothing
    uv run python -m scripts.record_label_samples --yes    # reads them (about $0.002 on Haiku)

The photos are in web/public/label-samples/ (see its README for their sources); the samples
are listed in web/lib/label.ts (LABEL_SAMPLES). Each response is written beside them as
<slug>.json, and the page shows it at no cost, labelled as a recorded example. The read goes
through the real API code, against a database with the serving tables (the local one by
default), so matches and swaps are the same as on the site.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "web" / "public" / "label-samples"
LABEL_TS = ROOT / "web" / "lib" / "label.ts"
LOCAL_DB = "postgresql://labellens:labellens@localhost:54329/labellens"
EST_USD_PER_PHOTO = 0.0004  # Haiku, an upper bound (evals/results/label_reading_*.md)


def samples() -> list[tuple[str, list[str]]]:
    """(slug, photo paths) for each sample in LABEL_SAMPLES."""
    text = LABEL_TS.read_text("utf-8")
    block = text[text.index("LABEL_SAMPLES") :]
    found = []
    for match in re.finditer(r'slug: "([^"]+)".*?photos: \[([^\]]*)\]', block, re.S):
        photos = re.findall(r'"/label-samples/([^"]+)"', match.group(2))
        found.append((match.group(1), photos))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Record the sample label reads.")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--database-url", default=LOCAL_DB, help="a database with `serving`")
    args = parser.parse_args(argv)

    todo = samples()
    photos = sum(len(p) for _, p in todo)
    print(f"{len(todo)} samples, {photos} photos: about ${photos * EST_USD_PER_PHOTO:.4f}.")
    if not args.yes:
        print("Nothing sent. Add --yes to run it.")
        return 0

    from fastapi.testclient import TestClient

    from api.app.config import Settings
    from api.app.main import create_app

    app = create_app(Settings(database_url=args.database_url))  # pyright: ignore[reportCallIssue]
    with TestClient(app) as client:
        for slug, names in todo:
            files = [
                ("images", (name, (SAMPLES / name).read_bytes(), "image/jpeg")) for name in names
            ]
            response = client.post("/label", files=files)
            if response.status_code != 200:
                print(
                    f"  {slug}: HTTP {response.status_code} {response.text[:200]}", file=sys.stderr
                )
                return 1
            body = response.json()
            out = SAMPLES / f"{slug}.json"
            out.write_text(
                json.dumps(body, indent=2, ensure_ascii=False) + "\n", "utf-8", newline="\n"
            )
            label = body.get("label") or {}
            match = body.get("match") or {}
            print(f"  {slug}: {label.get('name')} -> {(match.get('product') or {}).get('code')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
