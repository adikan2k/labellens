"""Response models shared across endpoints. Mirrors docs/openapi.yaml."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

NutriscoreGrade = Literal["a", "b", "c", "d", "e"]


class Source(BaseModel):
    """Attribution carried by every response."""

    name: Literal["Open Food Facts"] = "Open Food Facts"
    url: str = "https://world.openfoodfacts.org"
    licence: Literal["ODbL-1.0"] = "ODbL-1.0"
    licence_url: str = "https://opendatacommons.org/licenses/odbl/1-0/"
    # Date of the loaded snapshot; null when the database cannot be reached.
    snapshot_date: date | None = None


class Error(BaseModel):
    detail: str
    source: Source


class Versions(BaseModel):
    api: str
    python: str


class Health(BaseModel):
    status: Literal["ok"]
    versions: Versions
    source: Source


class ProductSummary(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str | None
    brand: str | None
    category_main: str | None
    nutriscore_grade: NutriscoreGrade | None
    nova_group: Literal[1, 2, 3, 4] | None
    image_url: str | None


class SearchResult(ProductSummary):
    match: Literal["barcode", "name", "brand"]


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    source: Source
