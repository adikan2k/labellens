"""One product with everything the product page shows, in a single query.

Additive and ingredient ids are stored as ordered arrays; Postgres unnests them with their
position and joins the names, so label order survives.
"""

from __future__ import annotations

from typing import Any

from api.app.db import DictConnection
from api.app.search import summary

NUTRIENTS = (
    "energy_kcal_100g",
    "sugars_100g",
    "salt_100g",
    "fat_100g",
    "saturated_fat_100g",
    "fiber_100g",
    "proteins_100g",
)

PRODUCT_SQL = """
select
    p.*,
    c.name as category_name,
    coalesce((
        select jsonb_agg(jsonb_build_object(
                   'additive_id', a.additive_id, 'e_number', a.e_number, 'name', a.name,
                   'function', a.function, 'explainer', a.explainer,
                   'explainer_ai', a.explainer_ai, 'flagged', a.flagged)
               order by x.ord)
        from unnest(p.additive_ids) with ordinality as x(id, ord)
        join serving.additives a on a.additive_id = x.id
    ), '[]'::jsonb) as additives,
    coalesce((
        select jsonb_agg(jsonb_build_object(
                   'ingredient_id', i.ingredient_id, 'name', i.name, 'rank', x.ord,
                   'explainer', i.explainer, 'explainer_ai', i.explainer_ai)
               order by x.ord)
        from unnest(p.ingredient_ids) with ordinality as x(id, ord)
        join serving.ingredients i on i.ingredient_id = x.id
    ), '[]'::jsonb) as ingredients
from serving.products p
left join serving.categories c on c.category_id = p.category_id
where p.code = %(code)s
"""


def _with_explainer(item: dict[str, Any]) -> dict[str, Any]:
    """Fold the explainer columns into the contract's {text, ai_generated} object, or null."""
    out = dict(item)
    text = out.pop("explainer", None)
    ai = out.pop("explainer_ai", False)
    out["explainer"] = {"text": text, "ai_generated": bool(ai)} if text else None
    return out


def get_product(conn: DictConnection, code: str) -> dict[str, Any] | None:
    row = conn.execute(PRODUCT_SQL, {"code": code}).fetchone()
    if row is None:
        return None
    return {
        **summary(row),
        "category_name": row["category_name"],
        "category_source": row["category_source"],
        "completeness": row["completeness"],
        "nutrition": {n: row[n] for n in NUTRIENTS},
        "additives": [_with_explainer(a) for a in row["additives"]],
        "ingredients": [_with_explainer(i) for i in row["ingredients"]],
        "off_url": f"https://world.openfoodfacts.org/product/{row['code']}",
        "in_graph": row["in_graph"],
    }


def get_stats(conn: DictConnection) -> dict[str, Any] | None:
    row = conn.execute("select doc from serving.stats").fetchone()
    return row["doc"] if row else None
