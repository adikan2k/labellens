"""Structured output of the MCP tools: what the card renders and the output schema publishes.

Built from the API's own schemas (api/app/schemas.py) so the card, the web app and the API
describe a product the same way.
"""

from __future__ import annotations

from api.app.schemas import Model, ProductSummary, Source


class Listed(ProductSummary):
    """A product with its LabelLens page."""

    url: str


class SearchOutput(Model):
    query: str
    results: list[Listed]
    source: Source
