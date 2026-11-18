"""Product search: barcodes by prefix, names and brands by full-text search.

Text queries become a safe tsquery: only word characters survive, words are ANDed, and the
last word matches as a prefix so results appear while typing ("chee" finds Cheerios). Results
are ordered by rank_pos (set by the loader: English-language products, then scans, then
completeness), which the rank index serves without sorting every match.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from api.app.db import DictConnection

WORD = re.compile(r"[^\W_]+", re.UNICODE)
BARCODE = re.compile(r"^[\d\s-]+$")
MAX_WORDS = 8
MIN_BARCODE_DIGITS = 3
# One product is often listed several times (pack sizes, reformulations): text search fetches
# this many times the limit in rank order and keeps the first row per name and brand.
OVERFETCH = 4
IMAGE_BASE = "https://images.openfoodfacts.org/images/products/"

COLUMNS = "code, name, brand, category_id, nutriscore_grade, nova_group, image_path"

TEXT_SQL = f"""
select {COLUMNS}
from serving.products
where to_tsvector('english'::regconfig, name || ' ' || coalesce(brand, ''))
      @@ to_tsquery('english'::regconfig, %(query)s)
order by rank_pos
limit %(limit)s
"""

# Prefix ranges instead of LIKE ANY, which Postgres will not serve from an index. Codes are
# digits under C collation, so '~' sorts after every code that starts with the prefix.
BARCODE_SQL = f"""
select {COLUMNS}
from serving.products
where (code >= %(a)s and code < %(a)s || '~') or (code >= %(b)s and code < %(b)s || '~')
order by (code in (%(a)s, %(b)s)) desc, rank_pos
limit %(limit)s
"""


def image_url(path: str | None) -> str | None:
    return f"{IMAGE_BASE}{path}.400.jpg" if path else None


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD.findall(text)][:MAX_WORDS]


def to_tsquery(text: str) -> str | None:
    """'honey nut chee' -> 'honey & nut & chee:*'. None when nothing searchable is left."""
    found = words(text)
    if not found:
        return None
    return " & ".join([*found[:-1], f"{found[-1]}:*"])


def barcode_digits(text: str) -> str | None:
    stripped = text.strip()
    if not BARCODE.match(stripped):
        return None
    digits = re.sub(r"\D", "", stripped)
    return digits if len(digits) >= MIN_BARCODE_DIGITS else None


def _match(row: dict[str, Any], query_words: list[str]) -> Literal["name", "brand"]:
    name = (row["name"] or "").lower()
    return "name" if all(w in name for w in query_words) else "brand"


def summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": row["code"],
        "name": row["name"],
        "brand": row["brand"],
        "category_main": row["category_id"],
        "nutriscore_grade": row["nutriscore_grade"],
        "nova_group": row["nova_group"],
        "image_url": image_url(row["image_path"]),
    }


def search(conn: DictConnection, q: str, limit: int) -> list[dict[str, Any]]:
    digits = barcode_digits(q)
    if digits:
        # A 12-digit UPC is stored as a 13-digit EAN with a leading zero.
        other = f"0{digits}" if len(digits) == 12 else digits
        rows = conn.execute(BARCODE_SQL, {"a": digits, "b": other, "limit": limit}).fetchall()
        return [{**summary(r), "match": "barcode"} for r in rows]

    query = to_tsquery(q)
    if query is None:
        return []
    rows = conn.execute(TEXT_SQL, {"query": query, "limit": limit * OVERFETCH}).fetchall()
    query_words = words(q)
    return [{**summary(r), "match": _match(r, query_words)} for r in one_per_product(rows, limit)]


def one_per_product(rows: list[Any], limit: int) -> list[Any]:
    """The best-ranked row per name and brand, ignoring case, in the order given."""
    seen: set[tuple[str, str]] = set()
    kept = []
    for row in rows:
        key = ((row["name"] or "").casefold().strip(), (row["brand"] or "").casefold().strip())
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
        if len(kept) == limit:
            break
    return kept
