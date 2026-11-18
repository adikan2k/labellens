"""The one model call: a label photo in, the label's printed facts out, as structured output.

The model copies what is printed and nothing else. Conversions (per serving to per 100 g,
kJ, sodium) happen in `normalise`, in code, where they can be tested.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.app.config import input_cost_usd, price_per_mtok, thinking_off
from api.app.label.categories import LEAF_CATEGORIES
from api.app.label.images import Image

PROMPT_VERSION = "label-v2"
MAX_TOKENS = 1500
CALL_SECONDS = 30.0

CategoryId = Literal[tuple(LEAF_CATEGORIES)]  # type: ignore[valid-type]


class PrintedNutrition(BaseModel):
    """Values exactly as printed, in the column described by `basis`; null when not printed."""

    energy_kcal: float | None = Field(description="Calories (kcal). Null if only kJ is printed.")
    energy_kj: float | None = Field(description="Energy in kJ, if printed.")
    fat_g: float | None = Field(description="Total fat in grams.")
    saturated_fat_g: float | None = Field(description="Saturated fat in grams.")
    sodium_mg: float | None = Field(description="Sodium in milligrams, as US labels print it.")
    salt_g: float | None = Field(description="Salt in grams, as EU labels print it.")
    fiber_g: float | None = Field(description="Dietary fiber in grams.")
    sugars_g: float | None = Field(description="Total sugars in grams (not only added sugars).")
    protein_g: float | None = Field(description="Protein in grams.")


class LabelReading(BaseModel):
    is_food_label: bool = Field(
        description="True if the photos show the packaging of a food or drink product."
    )
    name: str | None = Field(description="The product name as printed, if visible.")
    brand: str | None = Field(description="The brand as printed, if visible.")
    barcode: str | None = Field(description="The barcode's digits if printed legibly, else null.")
    basis: Literal["per_100g", "per_serving", "unknown"] = Field(
        description="Which column the nutrition values come from. Prefer a per 100 g (or "
        "per 100 ml) column when one is printed; US labels usually print per serving only."
    )
    serving_size_g: float | None = Field(
        description="One serving in grams (or ml for drinks), from the serving size line."
    )
    nutrition: PrintedNutrition
    ingredients: list[str] = Field(
        description="Every ingredient in label order, short names without percentages. "
        "Sub-ingredients in parentheses follow their parent as separate items."
    )
    additives: list[str] = Field(
        description="The additives among the ingredients, each as its E-number (E330) when "
        "known, else its name as printed. Not flavors or plain foods."
    )
    category_id: CategoryId = Field(  # type: ignore[valid-type]
        description="The category that best fits the product; 'other' if none does."
    )


def _categories() -> str:
    return "\n".join(f"- {cid}: {name}" for cid, name in LEAF_CATEGORIES.items())


SYSTEM = f"""You read food labels from photos for LabelLens, which explains US food labels.

Copy what is printed. Never estimate, convert or fill in a value that is not legible: use null.
- Nutrition: take one column. If a per 100 g (or 100 ml) column is printed, use it and set
  basis to per_100g. Otherwise use the per serving column, set basis to per_serving, and give
  the serving size in grams (or ml). Ignore % Daily Value.
- Read each number from the same row as its nutrient's name; panels in two or three languages
  and side-by-side columns make it easy to take the neighbouring row's value.
- A value printed as "less than" (<0.5 g) is given as that bound (0.5).
- Sodium stays in mg as printed; salt stays in g. Don't convert one into the other.
- Ingredients: in label order, as short names ("wheat flour", "sugar", "soy lecithin").
- Additives: only the additives in the ingredient list. Give each as its E-number when you
  know it, even if the label prints only the name (xanthan gum is E415, sodium benzoate is
  E211, citric acid is E330); otherwise give the name as printed.
- If the photos are not of food or drink packaging, set is_food_label to false and leave the
  rest empty or null.

Categories:
{_categories()}"""


@dataclass
class ReadUsage:
    input_tokens: int = 0  # every input token, cached or not
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def cost(self, model: str) -> float:
        uncached = (
            self.input_tokens - self.cache_read_input_tokens - self.cache_creation_input_tokens
        )
        _, price_out = price_per_mtok(model)
        return (
            input_cost_usd(
                model, uncached, self.cache_read_input_tokens, self.cache_creation_input_tokens
            )
            + self.output_tokens * price_out / 1e6
        )


@dataclass
class ReadResult:
    reading: LabelReading
    usage: ReadUsage
    stop_reason: str | None


def request_params(model: str, images: list[Image]) -> dict[str, Any]:
    """The Messages API request, without the client. Image bytes go only to Anthropic."""
    content: list[dict[str, Any]] = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image.media_type,
                "data": base64.standard_b64encode(image.data).decode("ascii"),
            },
        }
        for image in images
    ]
    content.append({"type": "text", "text": "Read this food label."})
    return {
        "model": model,
        "max_tokens": MAX_TOKENS,
        "system": [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": content}],
        "thinking": thinking_off(model),
    }


class ReadFailed(Exception):
    """The model returned nothing usable (a refusal, or output cut off). It still cost."""

    def __init__(self, reason: str, usage: ReadUsage):
        super().__init__(reason)
        self.usage = usage


def read(
    client: Any, model: str, images: list[Image], *, timeout: float = CALL_SECONDS
) -> ReadResult:
    response = client.messages.parse(
        **request_params(model, images), output_format=LabelReading, timeout=timeout
    )
    usage = response.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    counted = ReadUsage(
        input_tokens=usage.input_tokens + cache_read + cache_write,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_write,
    )
    parsed = getattr(response, "parsed_output", None)
    if parsed is None:
        raise ReadFailed(response.stop_reason or "no output", counted)
    return ReadResult(parsed, counted, response.stop_reason)
