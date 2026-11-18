"""Structured output of the MCP tools: what the card renders and the output schema publishes.

Built from the API's own schemas (api/app/schemas.py) so the card, the web app and the API
describe a product the same way. `view` tells the card which layout to draw.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from api.app.schemas import Explainer, Model, Nutrition, ProductSummary, Source


class Listed(ProductSummary):
    """A product with its LabelLens page."""

    url: str


class SearchOutput(Model):
    query: str
    results: list[Listed]
    source: Source


class CardAdditive(Model):
    additive_id: str
    e_number: str | None
    name: str
    function: str | None
    # Open Food Facts marks a high overexposure risk (EFSA estimates)
    flagged: bool


class CardProduct(Listed):
    category_name: str | None
    nutrition: Nutrition
    additives: list[CardAdditive]
    off_url: str


class ProductOutput(Model):
    view: Literal["product"] = "product"
    product: CardProduct
    source: Source


class CardSwap(Model):
    product: Listed
    reason: str
    additive_count: int = Field(ge=0)


class SwapsOutput(Model):
    view: Literal["swaps"] = "swaps"
    product: Listed
    swaps: list[CardSwap]
    source: Source


class AdditiveOutput(Model):
    additive_id: str
    e_number: str | None
    name: str
    function: str | None
    explainer: Explainer | None
    flagged: bool
    source: Source
