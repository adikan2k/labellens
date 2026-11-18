"""One additive by whatever a person calls it: its id, its E-number or its name."""

from __future__ import annotations

import re
from typing import Any

from api.app.db import DictConnection

E_NUMBER = re.compile(r"^(?:en:)?e\s*-?\s*(\d{3,4})\s*([a-z]?)\s*(?:\(?([ivx]+)\)?)?$")
COLUMNS = "additive_id, e_number, name, function, explainer, explainer_ai, flagged"

# Exact id, then exact E-number, then exact name; else the shortest name holding every word.
EXACT_SQL = f"""
select {COLUMNS} from serving.additives
where additive_id = %(id)s or lower(e_number) = %(e)s or lower(name) = %(name)s
order by additive_id = %(id)s desc, lower(e_number) = %(e)s desc
limit 1
"""
# "E322" is stored as E322i: an E-number without its letter or roman suffix means its family.
FAMILY_SQL = f"""
select {COLUMNS} from serving.additives
where lower(e_number) like %(prefix)s
order by length(e_number), e_number
limit 1
"""
WORDS_SQL = f"""
select {COLUMNS} from serving.additives
where lower(name) like all(%(patterns)s)
order by length(name), name
limit 1
"""


# What US labels and shoppers call an additive when it isn't Open Food Facts' own name.
ALIASES = {
    "msg": "e621",  # monosodium glutamate
    "bha": "e320",  # butylated hydroxyanisole
    "bht": "e321",  # butylated hydroxytoluene
    "tbhq": "e319",  # tert-butylhydroquinone
    "edta": "e385",  # calcium disodium EDTA
    "acesulfame potassium": "e950",
    "ace-k": "e950",
    "baking soda": "e500",
    "sodium bicarbonate": "e500",
    "cellulose gel": "e460",
    "cellulose gum": "e466",
    "lecithin": "e322",
    "soy lecithin": "e322",
    "soya lecithin": "e322",
    "sunflower lecithin": "e322",
    "mixed tocopherols": "e306",
    "tocopherols": "e306",
    "stevia extract": "e960",
    "stevia leaf extract": "e960",
    "vitamin c": "e300",
}


def normalise(term: str) -> dict[str, str] | None:
    """The forms one term can take. None when nothing searchable is left."""
    text = " ".join(term.lower().split())
    if not text:
        return None
    text = ALIASES.get(text, text)
    match = E_NUMBER.match(text)
    if match:
        digits, letter, roman = match.groups()
        e = f"e{digits}{letter}{roman or ''}"
        return {"id": f"en:{e}", "e": e, "name": text, "prefix": f"e{digits}{letter}%"}
    return {"id": text if text.startswith("en:") else f"en:{text}", "e": text, "name": text}


def get_additive(conn: DictConnection, term: str) -> dict[str, Any] | None:
    forms = normalise(term)
    if forms is None:
        return None
    row = conn.execute(EXACT_SQL, forms).fetchone()
    if row is None and "prefix" in forms:
        row = conn.execute(FAMILY_SQL, forms).fetchone()
    if row is None and "prefix" not in forms:
        words = re.findall(r"[a-z0-9]+", forms["name"])
        if words:
            patterns = [f"%{w}%" for w in words]
            row = conn.execute(WORDS_SQL, {"patterns": patterns}).fetchone()
    return dict(row) if row else None


def flagged_ids(conn: DictConnection, additive_ids: list[str]) -> set[str]:
    """Which of these additives Open Food Facts flags for a high overexposure risk."""
    if not additive_ids:
        return set()
    rows = conn.execute(
        "select additive_id from serving.additives where flagged and additive_id = any(%s)",
        [additive_ids],
    ).fetchall()
    return {r["additive_id"] for r in rows}
