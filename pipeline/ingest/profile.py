"""Profile a food.parquet snapshot and write docs/data-profile.md.

Step 1, find the US filter (prints candidate columns, writes nothing):

    uv run python -m pipeline.ingest.profile --candidates

Step 2, once the filter is agreed, write the profile:

    uv run python -m pipeline.ingest.profile --us-filter "<SQL predicate>"

Every column gets its type, null and empty rates over all rows and over US rows, and five sample
values from US rows. Later phases take column names from the profile, never from memory.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
PROFILE_PATH = ROOT / "docs" / "data-profile.md"
SAMPLE_ROWS = 20_000
SEED = 42
SAMPLE_WIDTH = 80


@dataclass(frozen=True)
class Column:
    name: str
    type: str
    null_all: float
    null_us: float
    empty_all: float | None
    empty_us: float | None
    samples: list[str]


@dataclass
class Profile:
    rows: int
    us_rows: int
    us_filter: str
    columns: list[Column] = field(default_factory=list)


@dataclass(frozen=True)
class Candidate:
    name: str
    type: str
    matching_rows: int
    top_values: list[tuple[str, int]]


def q(name: str) -> str:
    """Quote an identifier for DuckDB."""
    return '"' + name.replace('"', '""') + '"'


def _is_list(type_: str) -> bool:
    return type_.endswith("[]") or type_.startswith("LIST")


def _empty_expr(name: str, type_: str) -> str | None:
    if type_ == "VARCHAR":
        return f"trim({q(name)}) = ''"
    if _is_list(type_):
        return f"len({q(name)}) = 0"
    return None


def latest_snapshot(raw_dir: Path = RAW_DIR) -> Path:
    snapshots = sorted(p for p in raw_dir.glob("*/food.parquet") if p.is_file())
    if not snapshots:
        raise SystemExit(f"No snapshot under {raw_dir}. Run pipeline.ingest.snapshot first.")
    return snapshots[-1]


def connect(temp_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    if temp_dir is not None:
        temp_dir.mkdir(parents=True, exist_ok=True)
        con.execute(f"SET temp_directory = '{temp_dir.as_posix()}'")
    con.execute("SET preserve_insertion_order = false")
    return con


def describe(con: duckdb.DuckDBPyConnection, path: Path) -> list[tuple[str, str]]:
    rows = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path.as_posix()}')").fetchall()
    return [(str(r[0]), str(r[1])) for r in rows]


def find_candidates(
    con: duckdb.DuckDBPyConnection, path: Path, pattern: str = "countr"
) -> list[Candidate]:
    """Columns whose name contains `pattern`, with rows mentioning the United States."""
    src = f"read_parquet('{path.as_posix()}')"
    found = []
    for name, type_ in describe(con, path):
        if pattern not in name.lower():
            continue
        value = f"unnest({q(name)})" if _is_list(type_) else q(name)
        top = con.execute(
            f"SELECT v::VARCHAR, count(*) AS n FROM (SELECT {value} AS v FROM {src}) "
            "WHERE v IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 12"
        ).fetchall()
        matching = con.execute(
            f"SELECT count(*) FROM {src} "
            f"WHERE {q(name)}::VARCHAR ILIKE '%united%states%' OR {q(name)}::VARCHAR ILIKE '%usa%'"
        ).fetchone()
        found.append(
            Candidate(
                name, type_, int(matching[0]) if matching else 0, [(str(v), int(n)) for v, n in top]
            )
        )
    return found


def _pct(part: int, whole: int) -> float:
    return 0.0 if whole == 0 else 100.0 * part / whole


def _clean(value: Any) -> str:
    text = " ".join(str(value).split())
    if len(text) > SAMPLE_WIDTH:
        text = text[: SAMPLE_WIDTH - 1] + "…"
    return text.replace("|", "\\|")


def build_profile(
    con: duckdb.DuckDBPyConnection,
    path: Path,
    us_filter: str,
    *,
    sample_rows: int = SAMPLE_ROWS,
    seed: int = SEED,
) -> Profile:
    src = f"read_parquet('{path.as_posix()}')"
    columns = describe(con, path)

    # One scan for every count: nulls and empties, over all rows and over US rows.
    exprs = ["count(*)", f"count(*) FILTER (WHERE {us_filter})"]
    for name, type_ in columns:
        exprs.append(f"count(*) FILTER (WHERE {q(name)} IS NULL)")
        exprs.append(f"count(*) FILTER (WHERE {q(name)} IS NULL AND ({us_filter}))")
        empty = _empty_expr(name, type_)
        if empty:
            exprs.append(f"count(*) FILTER (WHERE {empty})")
            exprs.append(f"count(*) FILTER (WHERE {empty} AND ({us_filter}))")
    counts = con.execute(f"SELECT {', '.join(exprs)} FROM {src}").fetchone()
    assert counts is not None
    rows, us_rows = int(counts[0]), int(counts[1])
    profile = Profile(rows=rows, us_rows=us_rows, us_filter=us_filter)

    # Samples come from a fixed-seed reservoir of US rows, so reruns show the same values.
    con.execute(
        f"CREATE OR REPLACE TEMP TABLE us_sample AS SELECT * FROM {src} WHERE {us_filter} "
        f"USING SAMPLE reservoir({sample_rows} ROWS) REPEATABLE ({seed})"
    )

    i = 2
    for name, type_ in columns:
        null_all, null_us = int(counts[i]), int(counts[i + 1])
        i += 2
        empty_all = empty_us = None
        empty = _empty_expr(name, type_)
        if empty:
            empty_all, empty_us = _pct(int(counts[i]), rows), _pct(int(counts[i + 1]), us_rows)
            i += 2
        not_empty = f"AND NOT ({empty})" if empty else ""
        samples = con.execute(
            f"SELECT DISTINCT {q(name)}::VARCHAR AS v FROM us_sample "
            f"WHERE {q(name)} IS NOT NULL {not_empty} ORDER BY v LIMIT 5"
        ).fetchall()
        profile.columns.append(
            Column(
                name=name,
                type=type_,
                null_all=_pct(null_all, rows),
                null_us=_pct(null_us, us_rows),
                empty_all=empty_all,
                empty_us=empty_us,
                samples=[_clean(s[0]) for s in samples],
            )
        )
    return profile


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def render(profile: Profile, manifest: dict[str, Any], command: str) -> str:
    us_share = _pct(profile.us_rows, profile.rows)
    lines = [
        "# Data profile: food.parquet",
        "",
        f"Generated by `{command}` on {datetime.now(UTC):%Y-%m-%d}. Do not edit by hand; rerun it.",
        "Later phases take column names from this file.",
        "",
        "| Snapshot | |",
        "| --- | --- |",
        f"| Snapshot date | {manifest.get('snapshot_date', 'unknown')} |",
        f"| Dataset commit | `{manifest.get('dataset_commit', 'unknown')}` |",
        f"| Source | {manifest.get('source_url', 'unknown')} |",
        f"| File size | {int(manifest.get('bytes', 0)):,} bytes |",
        f"| SHA-256 | `{manifest.get('sha256', 'unknown')}` |",
        f"| Rows | {profile.rows:,} |",
        f"| Columns | {len(profile.columns)} |",
        f"| US filter | `{profile.us_filter}` |",
        f"| US rows | {profile.us_rows:,} ({us_share:.1f}% of rows) |",
        "",
        "## Columns",
        "",
        "Rates are percentages. Empty means an empty or blank string, or an empty list; "
        "`n/a` where emptiness does not apply. Samples are up to five distinct non-empty values "
        f"from a fixed-seed sample of {SAMPLE_ROWS:,} US rows, cut to {SAMPLE_WIDTH} characters.",
        "",
        "| Column | Type | Null all | Null US | Empty all | Empty US | Sample values (US) |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for c in profile.columns:
        samples = " · ".join(f"`{s}`" for s in c.samples) if c.samples else "(none)"
        lines.append(
            f"| `{c.name}` | `{_clean(c.type)}` | {c.null_all:.1f} | {c.null_us:.1f} | "
            f"{_fmt_rate(c.empty_all)} | {_fmt_rate(c.empty_us)} | {samples} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile a food.parquet snapshot.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--candidates", action="store_true", help="list possible US filter columns")
    mode.add_argument("--us-filter", help="SQL predicate selecting US products")
    parser.add_argument("--snapshot", type=Path, help="path to food.parquet (default: latest)")
    parser.add_argument("--out", type=Path, default=PROFILE_PATH)
    args = parser.parse_args(argv)

    path: Path = args.snapshot or latest_snapshot()
    con = connect(ROOT / "data" / "tmp")
    print(f"Snapshot: {path}", file=sys.stderr)

    if args.candidates:
        for c in find_candidates(con, path):
            print(f"\n{c.name}  ({c.type})  rows mentioning the US: {c.matching_rows:,}")
            for value, n in c.top_values:
                print(f"  {n:>10,}  {value[:100]}")
        return 0

    manifest_path = path.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8")) if manifest_path.exists() else {}
    profile = build_profile(con, path, args.us_filter)
    command = f'uv run python -m pipeline.ingest.profile --us-filter "{args.us_filter}"'
    args.out.write_text(render(profile, manifest, command), encoding="utf-8")
    print(f"Wrote {args.out}: {profile.rows:,} rows, {profile.us_rows:,} US rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
