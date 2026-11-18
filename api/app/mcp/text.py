"""The plain-text results the model reads, and the only output for clients without UI.

Numbers print as the website prints them (web/lib/format.ts): "380 kcal", "<0.1 g", "2.5 g",
"12 g". Every result ends with the ODbL attribution and the snapshot date.
"""

from __future__ import annotations

from api.app.mcp.models import AdditiveOutput, CardProduct, Listed, SwapsOutput
from api.app.schemas import Nutrition, Source

GRADES = {"a": "A", "b": "B", "c": "C", "d": "D", "e": "E"}
NOVA = {
    1: "unprocessed or minimally processed",
    2: "processed culinary ingredients",
    3: "processed foods",
    4: "ultra-processed foods",
}
NUTRIENTS: list[tuple[str, str]] = [
    ("fat_100g", "fat"),
    ("saturated_fat_100g", "saturated fat"),
    ("sugars_100g", "sugars"),
    ("salt_100g", "salt"),
    ("fiber_100g", "fiber"),
    ("proteins_100g", "protein"),
]
FLAG_NOTE = "flagged by Open Food Facts for a high overexposure risk"


def attribution(source: Source) -> str:
    day = source.snapshot_date
    when = f", snapshot of {day:%B} {day.day}, {day.year}" if day else ""
    return f"Data: Open Food Facts, under the Open Database License (ODbL){when}."


def grams(value: float) -> str:
    if value == 0:
        return "0 g"
    if value < 0.05:
        return "<0.1 g"
    if value < 10:
        return f"{round(value, 1):g} g"
    return f"{round(value)} g"


def grade(value: str | None) -> str:
    return f"Nutri-Score {GRADES[value]}" if value else "no Nutri-Score"


def named(product: Listed) -> str:
    name = product.name or "Unnamed product"
    return f"{name} ({product.brand})" if product.brand else name


def nova(group: int | None) -> str:
    return f"NOVA {group}: {NOVA[group]}" if group else "no NOVA group"


def nutrition(n: Nutrition) -> str:
    parts = []
    if n.energy_kcal_100g is not None:
        parts.append(f"energy {round(n.energy_kcal_100g)} kcal")
    parts += [
        f"{label} {grams(v)}" for key, label in NUTRIENTS if (v := getattr(n, key)) is not None
    ]
    missing = [label for key, label in NUTRIENTS if getattr(n, key) is None]
    line = "Per 100 g: " + (", ".join(parts) if parts else "no nutrition values listed") + "."
    if parts and missing:
        line += f" Not listed: {', '.join(missing)}."
    return line


def product_text(product: CardProduct, source: Source) -> str:
    where = f", {product.category_name}" if product.category_name else ""
    lines = [
        f"{named(product)}, barcode {product.code}{where}.",
        f"{grade(product.nutriscore_grade)}; {nova(product.nova_group)}.",
        nutrition(product.nutrition),
    ]
    if product.additives:
        items = [f"{a.e_number} {a.name}" if a.e_number else a.name for a in product.additives]
        flagged = [a.e_number or a.name for a in product.additives if a.flagged]
        lines.append(f"Additives ({len(items)}): {'; '.join(items)}.")
        if flagged:
            lines.append(f"{', '.join(flagged)}: {FLAG_NOTE}.")
    else:
        lines.append("No additives listed.")
    lines += [f"LabelLens page: {product.url}", "", attribution(source)]
    return "\n".join(lines)


def swaps_text(output: SwapsOutput) -> str:
    product = output.product
    head = f"{named(product)}, barcode {product.code}, {grade(product.nutriscore_grade)}."
    if not output.swaps:
        body = [
            "No better swap in its category: nothing similar there has a better Nutri-Score "
            "without a flagged additive."
        ]
    else:
        body = [f"{len(output.swaps)} better swaps in the same category:"]
        body += [
            f"{i}. {named(s.product)}, barcode {s.product.code}: {s.reason}. {s.product.url}"
            for i, s in enumerate(output.swaps, 1)
        ]
    return "\n".join([head, *body, "", attribution(output.source)])


def additive_text(output: AdditiveOutput) -> str:
    title = f"{output.name} ({output.e_number})" if output.e_number else output.name
    lines = [f"{title}, Open Food Facts id {output.additive_id}."]
    lines.append(
        f"Used as: {output.function.lower()}." if output.function else "Function not listed."
    )
    if output.explainer:
        note = " (written by AI from Open Food Facts data)" if output.explainer.ai_generated else ""
        lines.append(f"In short{note}: {output.explainer.text}")
    lines.append(
        "Open Food Facts flags it for a high overexposure risk (EFSA estimates)."
        if output.flagged
        else "Not flagged by Open Food Facts."
    )
    return "\n".join([*lines, "", attribution(output.source)])
