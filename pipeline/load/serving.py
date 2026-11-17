"""Load the serving tables into Postgres (Neon) from the DuckDB marts.

    uv run python -m pipeline.load.serving --dry-run     # size estimate only, no connection
    uv run python -m pipeline.load.serving               # load into DATABASE_URL
    uv run python -m pipeline.load.serving --replace     # drop the live tables first (downtime)

The API reads only what is loaded here, in schema `serving`:

- products: one row per named US product (unnamed ones cannot be searched or shown). Nutrition
  is inline; additive and ingredient ids are ordered arrays instead of 4.6 million bridge rows;
  the image is stored as its path tail. rank_pos orders search results: English-language
  products first (scan counts are global, so a heavily scanned foreign product would otherwise
  outrank US ones), then scans, then completeness. Rows are written in rank order.
- additives, ingredients, categories: lookups. stats: the dashboard document. meta: snapshot.

Safety: the size is estimated from DuckDB before connecting, and the load stops above 800 MB
(Neon's free plan blocks writes past 1 GB). Tables are built in `serving_next` and swapped in
with one transaction, so readers never see a half-loaded table. If old plus new would pass
1 GB, it refuses unless --replace.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, LiteralString, cast

import duckdb
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
DUCKDB_PATH = ROOT / "data" / "labellens.duckdb"
SCHEMA, NEXT, OLD = "serving", "serving_next", "serving_old"
MAX_LOAD_BYTES = 800_000_000
MAX_DATABASE_BYTES = 1_000_000_000
BATCH = 20_000
NUTRIENTS = [
    "energy_kcal_100g",
    "sugars_100g",
    "salt_100g",
    "fat_100g",
    "saturated_fat_100g",
    "fiber_100g",
    "proteins_100g",
]
NOVA_LABELS = {
    1: "Unprocessed or minimally processed",
    2: "Processed culinary ingredients",
    3: "Processed foods",
    4: "Ultra-processed foods",
}
MIN_CATEGORY_PRODUCTS = 200  # dashboard per-category figures need enough products

DDL = f"""
create schema {NEXT};
create table {NEXT}.products (
    code text collate "C" primary key,
    name text not null,
    brand text,
    category_id text,
    nutriscore_grade text,
    nova_group smallint,
    completeness real,
    scans integer not null,
    image_path text,
    {", ".join(f"{n} real" for n in NUTRIENTS)},
    additive_ids text[] not null,
    ingredient_ids text[] not null,
    rank_pos integer not null
);
create table {NEXT}.additives (
    additive_id text primary key,
    e_number text,
    name text not null,
    function text,
    explainer text,
    explainer_ai boolean not null default false
);
create table {NEXT}.ingredients (
    ingredient_id text primary key,
    name text not null,
    explainer text,
    explainer_ai boolean not null default false
);
create table {NEXT}.categories (
    category_id text primary key,
    name text not null,
    parent_id text
);
create table {NEXT}.stats (
    id smallint primary key default 1 check (id = 1),
    doc jsonb not null
);
create table {NEXT}.meta (
    key text primary key,
    value text not null
);
"""

# Built after the bulk copy, which is much faster than maintaining them during it.
INDEXES = f"""
create index products_search on {NEXT}.products
    using gin (to_tsvector('english'::regconfig, name || ' ' || coalesce(brand, '')));
create index products_rank on {NEXT}.products (rank_pos);
"""

PRODUCTS_SQL = f"""
with additives as (
    select code,
           list(additive_id order by
                try_cast(regexp_extract(additive_id, ':e(\\d+)', 1) as integer) nulls last,
                additive_id) as ids
    from bridge_product_additives group by code
),
ingredients as (
    select code, list(ingredient_id order by rank) as ids
    from bridge_product_ingredients group by code
)
select
    p.code,
    p.name,
    p.brand,
    p.category_main,
    p.nutriscore_grade,
    p.nova_group,
    p.completeness,
    p.scans,
    regexp_extract(p.image_url, 'images/products/(.+)\\.400\\.jpg$', 1) as image_path,
    {", ".join(f"f.{n}" for n in NUTRIENTS)},
    coalesce(a.ids, []::varchar[]) as additive_ids,
    coalesce(i.ids, []::varchar[]) as ingredient_ids,
    row_number() over (
        order by (p.lang = 'en') desc, p.scans desc, p.completeness desc nulls last, p.code
    ) as rank_pos
from dim_products as p
join fct_nutrition as f using (code)
left join additives as a using (code)
left join ingredients as i using (code)
where p.name is not null
order by rank_pos
"""

# (DuckDB mart, columns, serving table)
LOOKUPS: list[tuple[str, tuple[str, ...], str]] = [
    ("dim_additives", ("additive_id", "e_number", "name", "function"), "additives"),
    ("dim_ingredients", ("ingredient_id", "name"), "ingredients"),
    ("dim_categories", ("category_id", "name", "parent_id"), "categories"),
]

PRODUCT_COLUMNS = [
    "code", "name", "brand", "category_id", "nutriscore_grade", "nova_group", "completeness",
    "scans", "image_path", *NUTRIENTS, "additive_ids", "ingredient_ids", "rank_pos",
]  # fmt: skip


@dataclass(frozen=True)
class Estimate:
    tables: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.tables.values())


def _mb(n: int | float) -> str:
    return f"{n / 1e6:,.1f} MB"


def estimate(con: duckdb.DuckDBPyConnection) -> Estimate:
    """Upper-end size of the serving tables in Postgres, from the DuckDB marts.

    Heap: 28 bytes of tuple and pointer overhead per row, text as length + 1, numbers at their
    width, arrays as a 24-byte header plus length + 4 per element, then 15% for page fill.
    Indexes: B-trees at 1.4x their keys; the full-text GIN index at 10 bytes per word.
    Each relation also has a 64 KB floor for page and map minimums, which only matter for
    small loads such as the test fixture.
    """
    floor = 64 * 1024
    row = con.execute(
        f"""
        with p as ({PRODUCTS_SQL})
        select
            count(*),
            sum(28 + strlen(code) + 1 + strlen(name) + 1 + coalesce(strlen(brand) + 1, 0)
                + coalesce(strlen(category_main) + 1, 0) + 2 + 2 + 4 + 4 + 4
                + coalesce(strlen(image_path) + 1, 0) + 7 * 4
                + 24 + coalesce(
                    list_sum(list_transform(additive_ids, lambda x: strlen(x) + 4)), 0)
                + 24 + coalesce(
                    list_sum(list_transform(ingredient_ids, lambda x: strlen(x) + 4)), 0)),
            sum(strlen(code) + 16),
            sum(len(string_split_regex(trim(name || ' ' || coalesce(brand, '')), '\\s+')))
        from p
        """
    ).fetchone()
    assert row is not None
    rows, heap, pk_keys, words = (int(v or 0) for v in row)
    lookup_bytes = 0
    for table, columns, _ in LOOKUPS:
        sizes = " + ".join(f"coalesce(strlen({c}::varchar), 0)" for c in columns)
        row = con.execute(f"select coalesce(sum(60 + {sizes}), 0) from {table}").fetchone()
        lookup_bytes += int(row[0]) if row else 0
    return Estimate(
        {
            "products (heap)": int(heap * 1.15) + floor,
            "products_pkey": int(pk_keys * 1.4) + floor,
            "products_rank": int(rows * 20 * 1.4) + floor,
            "products_search (GIN)": int(words * 10) + floor,
            "lookups, stats, meta": int(lookup_bytes * 1.5) + 2_000_000,
        }
    )


def _stats(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    def rows(query: str) -> list[tuple[Any, ...]]:
        return con.execute(query).fetchall()

    def one(query: str) -> Any:
        row = con.execute(query).fetchone()
        assert row is not None
        return row[0]

    nutriscore = [
        {"key": g, "label": f"Nutri-Score {g.upper()}" if g else "No Nutri-Score", "count": n}
        for g, n in rows(
            "select nutriscore_grade, count(*) from dim_products group by 1 "
            "order by nutriscore_grade nulls last"
        )
    ]
    nova = [
        {"key": str(g) if g else None, "label": NOVA_LABELS.get(g, "No NOVA group"), "count": n}
        for g, n in rows(
            "select nova_group, count(*) from dim_products "
            "group by 1 order by nova_group nulls last"
        )
    ]
    categories = [
        {"key": c, "label": name, "count": n}
        for c, name, n in rows(
            """select c.category_id, c.name, count(p.code) from dim_categories c
               left join dim_products p on p.category_main = c.category_id
               where c.category_id not in (
                   select parent_id from dim_categories where parent_id is not null)
               group by all order by 3 desc, 1"""
        )
    ]
    top_additives = [
        {"key": a, "label": f"{e} {name}" if e else name, "count": n}
        for a, e, name, n in rows(
            "select additive_id, e_number, name, product_count from dim_additives "
            "order by product_count desc, additive_id limit 15"
        )
    ]
    by_category = [
        {
            "category_id": c,
            "name": name,
            "graded_count": total,
            "grades": {"a": a, "b": b, "c": cc, "d": d, "e": e},
        }
        for c, name, total, a, b, cc, d, e in rows(
            f"""select c.category_id, c.name, count(p.nutriscore_grade),
                       count(*) filter (where p.nutriscore_grade = 'a'),
                       count(*) filter (where p.nutriscore_grade = 'b'),
                       count(*) filter (where p.nutriscore_grade = 'c'),
                       count(*) filter (where p.nutriscore_grade = 'd'),
                       count(*) filter (where p.nutriscore_grade = 'e')
                from dim_products p join dim_categories c on c.category_id = p.category_main
                group by all having count(p.nutriscore_grade) >= {MIN_CATEGORY_PRODUCTS}
                order by 1"""
        )
    ]
    sugars = [
        {"category_id": c, "name": name, "median": round(float(m), 1), "product_count": n}
        for c, name, m, n in rows(
            f"""select c.category_id, c.name, median(f.sugars_100g), count(f.sugars_100g)
                from dim_products p join fct_nutrition f using (code)
                join dim_categories c on c.category_id = p.category_main
                group by all having count(f.sugars_100g) >= {MIN_CATEGORY_PRODUCTS}
                order by 3 desc"""
        )
    ]
    return {
        "product_count": one("select count(*) from dim_products"),
        "named_product_count": one("select count(*) from dim_products where name is not null"),
        "brand_count": one("select count(distinct lower(brand)) from dim_products"),
        "category_count": len(categories),
        "additive_count": one("select count(*) from dim_additives"),
        "nutriscore": nutriscore,
        "nova": nova,
        "categories": categories,
        "top_additives": top_additives,
        "nutriscore_by_category": by_category,
        "median_sugars_by_category": sugars,
    }


def _meta(con: duckdb.DuckDBPyConnection) -> dict[str, str]:
    row = con.execute("select any_value(snapshot_dir) from base_off__us_products").fetchone()
    snapshot_dir = ROOT / str(row[0]) if row and row[0] else None
    manifest: dict[str, Any] = {}
    if snapshot_dir and (snapshot_dir / "manifest.json").exists():
        manifest = json.loads((snapshot_dir / "manifest.json").read_text("utf-8"))
    return {
        "snapshot_date": manifest.get("snapshot_date")
        or (snapshot_dir.name if snapshot_dir else ""),
        "dataset_commit": manifest.get("dataset_commit") or "",
        "loaded_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def _batches(cur: duckdb.DuckDBPyConnection, query: str) -> Iterator[list[tuple[Any, ...]]]:
    cur.execute(query)
    while rows := cur.fetchmany(BATCH):
        yield rows


def _copy(
    pg: psycopg.Connection, table: str, columns: list[str], batches: Iterator[list[tuple[Any, ...]]]
) -> int:
    count = 0
    statement = sql.SQL("copy {}.{} ({}) from stdin").format(
        sql.Identifier(NEXT),
        sql.Identifier(table),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
    )
    with pg.cursor() as cur, cur.copy(statement) as copy:
        for batch in batches:
            for row in batch:
                copy.write_row(row)
            count += len(batch)
    return count


def _schema_exists(pg: psycopg.Connection, name: str) -> bool:
    row = pg.execute("select 1 from pg_namespace where nspname = %s", [name]).fetchone()
    return row is not None


def load(
    duckdb_path: Path, database_url: str, *, replace: bool = False, log=print
) -> dict[str, int]:
    """Load everything and swap it in. Returns actual sizes in bytes per relation."""
    con = duckdb.connect(str(duckdb_path), read_only=True)
    try:
        est = estimate(con)
        log("Estimated size in Postgres:")
        for name, size in est.tables.items():
            log(f"  {name:<24} {_mb(size):>10}")
        log(f"  {'total':<24} {_mb(est.total):>10}   (limit {_mb(MAX_LOAD_BYTES)})")
        if est.total > MAX_LOAD_BYTES:
            raise SystemExit(
                f"Estimated {_mb(est.total)} is over the {_mb(MAX_LOAD_BYTES)} limit. Not loading."
            )

        stats, meta = _stats(con), _meta(con)
        with psycopg.connect(database_url, autocommit=True) as pg:
            current = pg.execute("select pg_database_size(current_database())").fetchone()[0]  # type: ignore[index]
            live = _schema_exists(pg, SCHEMA)
            if live and current + est.total > MAX_DATABASE_BYTES:
                if not replace:
                    raise SystemExit(
                        f"Database is {_mb(current)}; loading {_mb(est.total)} beside the live "
                        f"tables would pass {_mb(MAX_DATABASE_BYTES)}. "
                        "Rerun with --replace (brief downtime)."
                    )
                log(f"--replace: dropping live schema {SCHEMA} first")
                pg.execute(f"drop schema {SCHEMA} cascade")
                live = False

            pg.execute(f"drop schema if exists {NEXT} cascade")
            pg.execute(cast("LiteralString", DDL))  # built only from module constants
            started = time.perf_counter()
            with pg.transaction():
                cur = con.cursor()
                n = _copy(pg, "products", PRODUCT_COLUMNS, _batches(cur, PRODUCTS_SQL))
                log(f"products: {n:,} rows in {time.perf_counter() - started:.0f} s")
                for source, columns, target in LOOKUPS:
                    query = f"select {', '.join(columns)} from {source}"
                    _copy(pg, target, list(columns), _batches(cur, query))
                pg.execute(f"insert into {NEXT}.stats (doc) values (%s)", [json.dumps(stats)])
                for key, value in meta.items():
                    pg.execute(
                        f"insert into {NEXT}.meta (key, value) values (%s, %s)", [key, value]
                    )
            pg.execute(cast("LiteralString", INDEXES))
            pg.execute(f"analyze {NEXT}.products")
            log(f"Loaded and indexed in {time.perf_counter() - started:.0f} s")

            # The swap needs brief exclusive locks; fail loudly rather than wait forever behind
            # a reader that left a transaction open.
            pg.execute("set lock_timeout = '30s'")
            with pg.transaction():
                pg.execute(f"drop schema if exists {OLD} cascade")
                if live:
                    pg.execute(f"alter schema {SCHEMA} rename to {OLD}")
                pg.execute(f"alter schema {NEXT} rename to {SCHEMA}")
            pg.execute(f"drop schema if exists {OLD} cascade")

            sizes = {
                name: size
                for name, size in pg.execute(
                    """select c.relname, pg_total_relation_size(c.oid) from pg_class c
                       join pg_namespace n on n.oid = c.relnamespace
                       where n.nspname = %s and c.relkind in ('r', 'i') order by 2 desc""",
                    [SCHEMA],
                ).fetchall()
            }
            database = pg.execute("select pg_database_size(current_database())").fetchone()[0]  # type: ignore[index]
        log("Actual size in Postgres:")
        tables = {k: v for k, v in sizes.items() if not k.endswith(("_pkey", "_rank", "_search"))}
        for name, size in tables.items():
            log(f"  {name:<24} {_mb(size):>10}  (with indexes)")
        log(f"  {'database total':<24} {_mb(database):>10}")
        return {**sizes, "_database": database}
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the serving tables into Postgres.")
    parser.add_argument("--duckdb", type=Path, default=DUCKDB_PATH)
    parser.add_argument("--database-url", help="default: DATABASE_URL from the environment or .env")
    parser.add_argument("--dry-run", action="store_true", help="print the size estimate only")
    parser.add_argument("--replace", action="store_true", help="drop the live tables first")
    args = parser.parse_args(argv)

    if args.dry_run:
        with duckdb.connect(str(args.duckdb), read_only=True) as con:
            est = estimate(con)
        for name, size in est.tables.items():
            print(f"  {name:<24} {_mb(size):>10}")
        print(f"  {'total':<24} {_mb(est.total):>10}   (limit {_mb(MAX_LOAD_BYTES)})")
        return 0 if est.total <= MAX_LOAD_BYTES else 1

    url = args.database_url
    if not url:
        from api.app.config import get_settings

        secret = get_settings().database_url
        url = secret.get_secret_value() if secret else None
    if not url:
        print("No database: set DATABASE_URL in .env or pass --database-url.", file=sys.stderr)
        return 1
    load(args.duckdb, url, replace=args.replace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
