"""Better swaps: similar products in the same category, better Nutri-Score, no flagged additive.

SPEC's rule: same category, a better grade, no additive on the flag list, ranked by
Nutri-Score then fewest additives. The flag list is Open Food Facts' own: additives its
taxonomy marks as high overexposure risk (dim_additives.flagged). Candidates must also have a
real GS1 barcode (serving.products.gtin_valid): Open Food Facts lists restaurant menu items
and shop-weighed goods under 16-24 digit codes, and those are not swaps anyone can buy. And
they must have an ingredient list: without one their additives are unknown, not absent, and
"no additives, none flagged" would be a claim the data cannot back (about 60% of US products
have no ingredients entered).

Same category alone is too broad: "Sauces, dressings and condiments" would offer marinara
as a swap for mayonnaise. So candidates must also be similar by name, in tiers, each used
only if the ones before found too few:
1. they share the head word (the last word of the name before any comma, once generic words
   such as "classic" or "organic" are dropped: "Classic Mayo" -> mayo) and another name word;
2. they share the head word;
3. they share any other name word.
Within each tier the SPEC ranking applies (grade, fewest additives, then search rank). If
neither tier finds anything, there are no swaps: nothing is better than an unrelated product.

A product with no category, no grade, or grade A gets no swaps, and nor does "Other or
unclear", which is not a category anyone shops.
"""

from __future__ import annotations

import re
from typing import Any

from api.app.db import DictConnection
from api.app.search import summary

OTHER = "other"
# Rows fetched before removing repeats of the same name and brand (different pack sizes).
OVERFETCH = 8

ME_SQL = """
select code, name, category_id, nutriscore_grade, additive_count
from serving.products where code = %(code)s
"""

# The tsvector expression matches the products_search GIN index, which finds the name
# matches; the category, grade and flag conditions narrow them.
CANDIDATES_SQL = """
select code, name, brand, category_id, nutriscore_grade, nova_group, image_path, additive_count
from serving.products
where to_tsvector('english'::regconfig, name || ' ' || coalesce(brand, ''))
        @@ to_tsquery('english'::regconfig, %(words)s)
  and category_id = %(category)s
  and nutriscore_grade < %(grade)s
  and not has_flagged
  and gtin_valid
  and cardinality(ingredient_ids) > 0
  and code <> %(code)s
order by nutriscore_grade, additive_count, rank_pos
limit %(fetch)s
"""

WORD = re.compile(r"[a-z]{3,}")
# Words that describe a style or claim rather than what the product is.
GENERIC = frozenset(
    {
        "and",
        "bites",
        "brand",
        "choice",
        "classic",
        "extra",
        "family",
        "fat",
        "favorite",
        "flavor",
        "flavored",
        "flavour",
        "flavoured",
        "for",
        "free",
        "fresh",
        "from",
        "homemade",
        "less",
        "light",
        "lite",
        "low",
        "mini",
        "minis",
        "more",
        "natural",
        "organic",
        "original",
        "pack",
        "premium",
        "pure",
        "real",
        "reduced",
        "select",
        "simple",
        "simply",
        "size",
        "style",
        "the",
        "value",
        "with",
    }
)


def name_words(name: str) -> list[str]:
    """Meaningful words of the name's first part, in order; the last is the head word."""
    head = name.split(",")[0].casefold()
    return [w for w in WORD.findall(head) if w not in GENERIC]


def _additives(n: int) -> str:
    return "no additives" if n == 0 else f"{n} additive{'' if n == 1 else 's'}"


def reason(mine: dict[str, Any], swap: dict[str, Any]) -> str:
    """'Nutri-Score A instead of D · 1 additive instead of 4 · none flagged by Open Food Facts'."""
    parts = [
        f"Nutri-Score {swap['nutriscore_grade'].upper()} "
        f"instead of {mine['nutriscore_grade'].upper()}"
    ]
    theirs, ours = swap["additive_count"], mine["additive_count"]
    if theirs == ours:
        parts.append(f"{_additives(theirs)}, the same")
    else:
        parts.append(f"{_additives(theirs)} instead of {ours}")
    parts.append("none flagged by Open Food Facts")
    return " · ".join(parts)


def find_swaps(conn: DictConnection, code: str, limit: int) -> list[dict[str, Any]] | None:
    """Swaps for a product, or None if there is no such product."""
    mine = conn.execute(ME_SQL, {"code": code}).fetchone()
    if mine is None:
        return None
    if not mine["category_id"] or mine["category_id"] == OTHER or not mine["nutriscore_grade"]:
        return []
    words = name_words(mine["name"])
    if not words:
        return []
    head = words[-1]
    others = " | ".join(w for w in dict.fromkeys(words[:-1]) if w != head)
    tiers = [f"{head} & ({others})", head, others] if others else [head]

    rows: list[dict[str, Any]] = []
    for query in tiers:
        rows += conn.execute(
            CANDIDATES_SQL,
            {
                "words": query,
                "category": mine["category_id"],
                "grade": mine["nutriscore_grade"],
                "code": code,
                "fetch": limit * OVERFETCH,
            },
        ).fetchall()
        if len(rows) >= limit:
            break

    swaps, seen = [], set()
    for row in rows:
        key = ((row["name"] or "").casefold(), (row["brand"] or "").casefold())  # pack sizes
        if key in seen:
            continue
        seen.add(key)
        swaps.append(
            {
                "product": summary(row),
                "reason": reason(mine, row),
                "additive_count": row["additive_count"],
            }
        )
        if len(swaps) == limit:
            break
    return swaps


# For a label read from a photo that matches no product in the data: there is no grade to
# beat, so these are the category's well-graded products (A or B), similar by name where the
# name gives words, under the same rules as swaps (no flagged additive, a real barcode, an
# ingredient list). The page says that is all they are.
WELL_GRADED_SQL = """
select code, name, brand, category_id, nutriscore_grade, nova_group, image_path, additive_count
from serving.products
where category_id = %(category)s
  and nutriscore_grade in ('a', 'b')
  and not has_flagged
  and gtin_valid
  and cardinality(ingredient_ids) > 0
  and (%(words)s::text is null
       or to_tsvector('english'::regconfig, name || ' ' || coalesce(brand, ''))
          @@ to_tsquery('english'::regconfig, %(words)s))
order by nutriscore_grade, additive_count, rank_pos
limit %(fetch)s
"""


def well_graded_reason(row: dict[str, Any]) -> str:
    """'Nutri-Score A · 1 additive · none flagged by Open Food Facts'."""
    return " · ".join(
        [
            f"Nutri-Score {row['nutriscore_grade'].upper()}",
            _additives(row["additive_count"]),
            "none flagged by Open Food Facts",
        ]
    )


def well_graded_like(
    conn: DictConnection, category: str, name: str | None, limit: int
) -> list[dict[str, Any]]:
    """Well-graded products in a category, those sharing the name's head word first."""
    if not category or category == OTHER:
        return []
    words = name_words(name or "")
    tiers: list[str | None] = [words[-1]] if words else []
    tiers.append(None)  # then the whole category
    rows: list[dict[str, Any]] = []
    for query in tiers:
        params = {"category": category, "words": query, "fetch": limit * OVERFETCH}
        rows += conn.execute(WELL_GRADED_SQL, params).fetchall()
        if len(rows) >= limit:
            break
    out, seen = [], set()
    for row in rows:
        key = ((row["name"] or "").casefold(), (row["brand"] or "").casefold())
        if key in seen or row["code"] in {o["product"]["code"] for o in out}:
            continue
        seen.add(key)
        out.append(
            {
                "product": summary(row),
                "reason": well_graded_reason(row),
                "additive_count": row["additive_count"],
            }
        )
        if len(out) == limit:
            break
    return out
