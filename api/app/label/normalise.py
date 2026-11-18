"""Printed label values to the per 100 g figures the rest of LabelLens uses.

In code, not in the prompt: the model copies what is printed, and these conversions are
plain arithmetic that tests can pin down.
- Per serving becomes per 100 g with the serving size; without one it cannot be converted.
- kJ becomes kcal (4.184 kJ per kcal) when kcal is not printed.
- Sodium in mg becomes salt in g (salt = sodium x 2.5) when salt is not printed.
- The pipeline's bounds apply: below zero, over 100 g per 100 g, or over 900 kcal per 100 g
  cannot be true, so the value is dropped.
"""

from __future__ import annotations

from typing import Any

from api.app.label.reading import LabelReading, PrintedNutrition
from api.app.products import NUTRIENTS

KJ_PER_KCAL = 4.184
SALT_PER_SODIUM = 2.5
MAX_KCAL_100G = 900.0
MAX_GRAMS_100G = 100.0

NO_SERVING = (
    "The label gives values per serving, but the serving size wasn't legible, so they can't "
    "be shown per 100 g."
)


def _grams(value: float | None) -> float | None:
    return value if value is not None and 0 <= value <= MAX_GRAMS_100G else None


def _per_100g(printed: PrintedNutrition, factor: float) -> dict[str, float | None]:
    def scale(value: float | None) -> float | None:
        return None if value is None else round(value * factor, 2)

    kcal = printed.energy_kcal
    if kcal is None and printed.energy_kj is not None:
        kcal = printed.energy_kj / KJ_PER_KCAL
    salt = printed.salt_g
    if salt is None and printed.sodium_mg is not None:
        salt = printed.sodium_mg * SALT_PER_SODIUM / 1000
    energy = scale(kcal)
    return {
        "energy_kcal_100g": energy if energy is not None and 0 <= energy <= MAX_KCAL_100G else None,
        "sugars_100g": _grams(scale(printed.sugars_g)),
        "salt_100g": _grams(scale(salt)),
        "fat_100g": _grams(scale(printed.fat_g)),
        "saturated_fat_100g": _grams(scale(printed.saturated_fat_g)),
        "fiber_100g": _grams(scale(printed.fiber_g)),
        "proteins_100g": _grams(scale(printed.protein_g)),
    }


def _number(value: float) -> str:
    return f"{value:g}"


def nutrition_per_100g(reading: LabelReading) -> tuple[dict[str, Any], str | None]:
    """The seven nutrients per 100 g, and a note saying how they were derived (or why not)."""
    serving = reading.serving_size_g
    if reading.basis == "per_100g":
        return _per_100g(reading.nutrition, 1.0), None
    if serving and serving > 0:
        note = f"Converted from per serving ({_number(serving)} g) to per 100 g."
        return _per_100g(reading.nutrition, 100.0 / serving), note
    empty: dict[str, Any] = dict.fromkeys(NUTRIENTS)
    printed_any = any(v is not None for v in reading.nutrition.model_dump().values())
    return empty, NO_SERVING if printed_any else None
