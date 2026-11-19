"""POST /label behind the route: limits, the run log, the read, and what LabelLens adds.

- Limits: LABEL_RATE_LIMIT_PER_HOUR reads per client per rolling hour, counted from
  app.ask_runs rows of kind 'label', so they hold across instances and don't eat into the
  questions. Every kind shares the daily spend cap.
- Privacy: the photos go to Anthropic to be read and nowhere else. LabelLens keeps no copy,
  and the Langfuse trace records "[n images]" in their place.
- What it adds: explainers for the additives and ingredients it knows, Open Food Facts'
  overexposure flag, the product in our data the label most likely is (by barcode, else by
  brand and name, only when the words agree), and swaps or well-graded products like it.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from typing import Any

from api.app import additives as additives_module
from api.app import products, swaps
from api.app.ask.service import RATE_SQL, SPENT_SQL, START_SQL
from api.app.ask.tracing import Tracer
from api.app.db import Database, DictConnection
from api.app.label.categories import LEAF_CATEGORIES
from api.app.label.images import Image
from api.app.label.normalise import nutrition_per_100g
from api.app.label.reading import PROMPT_VERSION, LabelReading, ReadFailed, ReadUsage, read
from api.app.search import search

log = logging.getLogger("labellens.label")

KIND = "label"
SUGGESTIONS = 5
NAME_AGREEMENT = 0.6  # share of the label's name words a product's name must also have

FINISH_SQL = """
update app.ask_runs set outcome = %(outcome)s, input_tokens = %(input_tokens)s,
    output_tokens = %(output_tokens)s, cost_usd = %(cost)s, duration_ms = %(duration_ms)s
where id = %(id)s
"""
INGREDIENTS_SQL = """
select ingredient_id, name, explainer, explainer_ai from serving.ingredients
where lower(name) = any(%(names)s)
"""
ADDITIVE_NAMES_SQL = f"""
select {additives_module.COLUMNS} from serving.additives where lower(name) = any(%(names)s)
"""

OVER_CAP = (
    "Today's budget for reading labels is used up. Try a sample label, or come back tomorrow (UTC)."
)
READ_FAILED = "That photo couldn't be read. Try a closer, sharper photo of the label."
UNAVAILABLE = "The label reader isn't answering right now. Try again in a minute."


class OverCap(Exception):
    pass


class LabelError(Exception):
    """A read that failed; `status` and the message go to the client."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


@dataclass
class LabelLimits:
    per_hour: int
    daily_cap_usd: float


_WORD = re.compile(r"[^\W_]{3,}", re.UNICODE)


def _words(text: str | None) -> set[str]:
    return set(_WORD.findall((text or "").casefold()))


def names_agree(reading: LabelReading, row: dict[str, Any]) -> bool:
    """Whether a search hit is plausibly the photographed product: most of the label's name
    words are in the product's name, and the brands share a word when both are known."""
    label = set(swaps.name_words(reading.name or "")) or _words(reading.name)
    if not label:
        return False
    theirs = _words(row.get("name"))
    if len(label & theirs) / len(label) < NAME_AGREEMENT:
        return False
    if reading.brand and row.get("brand"):
        return bool(_words(reading.brand) & _words(row["brand"]))
    return True


def _strip_zeros(code: str) -> str:
    return code.lstrip("0")


def match_product(conn: DictConnection, reading: LabelReading) -> tuple[str, str] | None:
    """(code, how) for the product the label most likely is, or None."""
    digits = re.sub(r"\D", "", reading.barcode or "")
    if 8 <= len(digits) <= 14:
        for row in search(conn, digits, 3):
            if _strip_zeros(row["code"]) == _strip_zeros(digits):
                return row["code"], "barcode"
    if reading.name:
        query = " ".join(part for part in (reading.brand, reading.name) if part)
        for row in search(conn, query, 5):
            if names_agree(reading, row):
                return row["code"], "name"
    return None


_PARENS = re.compile(r"\(([^)]*)\)")


def name_forms(name: str) -> list[str]:
    """An ingredient name as printed, without its brackets, and what the brackets hold:
    "ascorbic acid (vitamin c)" gives all three."""
    outside = " ".join(_PARENS.sub(" ", name).split())
    inside = [" ".join(part.split()) for part in _PARENS.findall(name)]
    return [form for form in dict.fromkeys([name, outside, *inside]) if form]


def _fold(item: dict[str, Any]) -> dict[str, Any]:
    out = dict(item)
    text = out.pop("explainer", None)
    ai = out.pop("explainer_ai", False)
    out["explainer"] = {"text": text, "ai_generated": bool(ai)} if text else None
    return out


def explain(conn: DictConnection, reading: LabelReading) -> dict[str, Any]:
    """Ingredients with our explainers, and the additives we know (with the flag)."""
    printed = [" ".join(i.split()) for i in reading.ingredients if i and i.strip()]
    lowered = [i.casefold() for i in printed]
    known = {
        row["name"].casefold(): row
        for row in conn.execute(INGREDIENTS_SQL, {"names": lowered}).fetchall()
    }
    ingredients = []
    for rank, name in enumerate(printed, start=1):
        row = known.get(name.casefold())
        ingredients.append(
            {
                "ingredient_id": row["ingredient_id"] if row else f"label:{rank}",
                "name": name[:1].upper() + name[1:],
                "rank": rank,
                "explainer": _fold(row)["explainer"] if row else None,
            }
        )

    found: dict[str, dict[str, Any]] = {}
    unmatched: list[str] = []
    for term in reading.additives:
        # "tocopherols (vitamin E)": the whole term, then without and inside its brackets.
        row = None
        for form in name_forms(" ".join(term.split()).casefold()):
            row = additives_module.get_additive(conn, form)
            if row is not None:
                break
        if row is None:
            unmatched.append(term)
        else:
            found.setdefault(row["additive_id"], row)
    # The model sometimes leaves an additive out of its list, so the ingredients are checked
    # too: by exact name or a known alias only (never the fuzzy word match, which would turn
    # "salt" into some additive with salt in its name).
    forms = [form for name in lowered for form in name_forms(name)]
    for form in forms:
        if form in additives_module.ALIASES:
            row = additives_module.get_additive(conn, form)
            if row is not None:
                found.setdefault(row["additive_id"], row)
    for row in conn.execute(ADDITIVE_NAMES_SQL, {"names": forms}).fetchall():
        found.setdefault(row["additive_id"], row)
    known_names = {row["name"].casefold() for row in found.values()}
    unmatched = [t for t in unmatched if t.casefold() not in known_names]
    additives = [_fold(row) | {"flagged": bool(row["flagged"])} for row in found.values()]
    return {"ingredients": ingredients, "additives": additives, "unmatched_additives": unmatched}


@dataclass
class LabelService:
    db: Database  # owner role: reads serving, writes app.ask_runs
    client: Any
    model: str
    tracer: Tracer
    limits: LabelLimits
    hash_key: bytes
    snapshot: Callable[[], Any]

    def _conn(self) -> AbstractContextManager[DictConnection]:
        return contextmanager(self.db.connection)()

    def retry_after(self, who: str) -> int | None:
        with self._conn() as conn:
            row = conn.execute(RATE_SQL, [who, KIND]).fetchone()
        if row and row["n"] >= self.limits.per_hour:
            return max(1, int(float(row["wait"] or 0)) + 1)
        return None

    def reads_left(self, who: str) -> int:
        with self._conn() as conn:
            row = conn.execute(RATE_SQL, [who, KIND]).fetchone()
        return max(0, self.limits.per_hour - int(row["n"] if row else 0))

    def spent_today(self) -> float:
        with self._conn() as conn:
            row = conn.execute(SPENT_SQL).fetchone()
        return float(row["spent"]) if row else 0.0

    def _start(self, who: str) -> int:
        with self._conn() as conn:
            row = conn.execute(START_SQL, [who, self.model, PROMPT_VERSION, KIND]).fetchone()
        assert row
        return int(row["id"])

    def _finish(self, run_id: int, outcome: str, usage: ReadUsage | None, started: float) -> None:
        values = {
            "id": run_id,
            "outcome": outcome,
            "input_tokens": usage.input_tokens if usage else 0,
            "output_tokens": usage.output_tokens if usage else 0,
            "cost": round(usage.cost(self.model), 6) if usage else 0,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
        try:
            with self._conn() as conn:
                conn.execute(FINISH_SQL, values)
        except Exception:
            log.warning("Could not finish label run %s", run_id, exc_info=True)

    def read(self, images: list[Image], who: str) -> dict[str, Any]:
        """Read one label. The caller checked the rate limit; this checks the daily cap."""
        started = time.monotonic()
        run_id = self._start(who)
        if self.spent_today() >= self.limits.daily_cap_usd:
            self._finish(run_id, "over_cap", None, started)
            raise OverCap(OVER_CAP)

        placeholder = f"[{len(images)} image{'s' if len(images) != 1 else ''}]"
        trace = self.tracer.trace("label", input=placeholder, metadata={"prompt": PROMPT_VERSION})
        generation = trace.child(
            "model call",
            "generation",
            model=self.model,
            input=[{"role": "user", "content": f"{placeholder} Read this food label."}],
        )
        outcome, usage = "internal", None
        try:
            try:
                result = read(self.client, self.model, images)
            except ReadFailed as failure:
                outcome, usage = "failed", failure.usage
                raise LabelError(422, READ_FAILED) from failure
            except LabelError:
                raise
            except Exception as error:  # the API timed out, was overloaded, or refused the key
                log.warning("label read failed: %s", error)
                outcome = "unavailable"
                raise LabelError(503, UNAVAILABLE) from error
            usage = result.usage
            reading = result.reading
            generation.end(
                output=reading.model_dump(),
                usage_details={
                    "input": usage.input_tokens
                    - usage.cache_read_input_tokens
                    - usage.cache_creation_input_tokens,
                    "input_cache_read": usage.cache_read_input_tokens,
                    "input_cache_creation": usage.cache_creation_input_tokens,
                    "output": usage.output_tokens,
                },
                cost_details={"total": usage.cost(self.model)},
                metadata={"stop_reason": result.stop_reason},
            )
            response = self._respond(reading)
            outcome = "answer" if reading.is_food_label else "not_label"
            trace.end(output={"name": reading.name, "matched": bool(response["match"])})
            return response
        except LabelError as error:
            trace.end(level="ERROR", status_message=str(error))
            raise
        finally:
            self._finish(run_id, outcome, usage, started)
            self.tracer.flush()

    def _respond(self, reading: LabelReading) -> dict[str, Any]:
        source = self.snapshot()
        if not reading.is_food_label:
            return {
                "is_food_label": False,
                "label": None,
                "match": None,
                "suggestions": [],
                "suggestions_kind": None,
                "source": source,
            }
        nutrition, note = nutrition_per_100g(reading)
        with self._conn() as conn:
            explained = explain(conn, reading)
            matched = match_product(conn, reading)
            product = products.get_product(conn, matched[0]) if matched else None
            if product is not None:
                suggestions = swaps.find_swaps(conn, product["code"], SUGGESTIONS) or []
                kind = "swaps"
            else:
                suggestions = swaps.well_graded_like(
                    conn, reading.category_id, reading.name, SUGGESTIONS
                )
                kind = "category"
        label = {
            "name": reading.name,
            "brand": reading.brand,
            "barcode": re.sub(r"\D", "", reading.barcode or "") or None,
            "category_id": reading.category_id,
            "category_name": LEAF_CATEGORIES.get(reading.category_id),
            "basis": reading.basis,
            "serving_size_g": reading.serving_size_g,
            "conversion_note": note,
            "nutrition": nutrition,
            **explained,
        }
        return {
            "is_food_label": True,
            "label": label,
            "match": {"how": matched[1], "product": product} if matched and product else None,
            "suggestions": suggestions,
            "suggestions_kind": kind if suggestions else None,
            "source": source,
        }
