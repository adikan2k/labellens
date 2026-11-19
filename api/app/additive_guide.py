"""The additive guide: every additive US products list, how common it is, where it is used.

The counts, top categories and example barcodes are computed in the pipeline
(agg_additive_usage) and stored on serving.additives, so a page is three small reads by key.
"""

from __future__ import annotations

from typing import Any

from api.app.db import DictConnection
from api.app.search import COLUMNS, summary

LIST_SQL = """
select additive_id, e_number, name, function, flagged, product_count
from serving.additives
where product_count > 0
order by product_count desc, name
"""

ONE_SQL = """
select a.additive_id, a.e_number, a.name, a.function, a.flagged, a.explainer, a.explainer_ai,
       a.product_count, a.example_codes,
       coalesce((
           select jsonb_agg(jsonb_build_object(
                      'category_id', c->>'category_id', 'name', k.name,
                      'products', (c->>'products')::int)
                  order by x.ord)
           from jsonb_array_elements(a.top_categories) with ordinality as x(c, ord)
           join serving.categories k on k.category_id = c->>'category_id'
       ), '[]'::jsonb) as top_categories
from serving.additives a
where a.additive_id = %(id)s
"""

PRODUCTS_SQL = f"select {COLUMNS} from serving.products where code = any(%(codes)s)"
# Named products, as counted by the pipeline (fct_stats), so a page never counts the table.
TOTAL_SQL = "select (doc->>'named_product_count')::int as n from serving.stats"


def slug(additive_id: str) -> str:
    """The additive's address in the guide: its Open Food Facts id without "en:"."""
    return additive_id[3:] if additive_id.startswith("en:") else additive_id


def additive_id(slug_: str) -> str:
    return slug_ if ":" in slug_ else f"en:{slug_}"


def _item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "additive_id": row["additive_id"],
        "slug": slug(row["additive_id"]),
        "e_number": row["e_number"],
        "name": row["name"],
        "function": row["function"],
        "flagged": bool(row["flagged"]),
        "product_count": row["product_count"],
    }


def list_additives(conn: DictConnection) -> list[dict[str, Any]]:
    """Every additive at least one named product lists, most common first."""
    return [_item(row) for row in conn.execute(LIST_SQL).fetchall()]


def get_guide(conn: DictConnection, slug_: str) -> dict[str, Any] | None:
    row = conn.execute(ONE_SQL, {"id": additive_id(slug_)}).fetchone()
    if row is None:
        return None
    codes = list(row["example_codes"] or [])
    found = {r["code"]: r for r in conn.execute(PRODUCTS_SQL, {"codes": codes}).fetchall()}
    total = conn.execute(TOTAL_SQL).fetchone()
    text = row["explainer"]
    return {
        **_item(row),
        "explainer": {"text": text, "ai_generated": bool(row["explainer_ai"])} if text else None,
        "share_of_products": (
            round(row["product_count"] / total["n"], 4) if total and total["n"] else 0.0
        ),
        "top_categories": row["top_categories"],
        "examples": [summary(found[c]) for c in codes if c in found],
    }
