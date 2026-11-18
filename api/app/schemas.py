"""Response models. Mirrors docs/openapi.yaml; api/tests/test_contract_match.py checks it."""

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NutriscoreGrade = Literal["a", "b", "c", "d", "e"]


class Model(BaseModel):
    # Fields with defaults are still always present in responses, as the contract says.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Source(Model):
    """Attribution carried by every response."""

    name: Literal["Open Food Facts"] = "Open Food Facts"
    url: str = "https://world.openfoodfacts.org"
    licence: Literal["ODbL-1.0"] = "ODbL-1.0"
    licence_url: str = "https://opendatacommons.org/licenses/odbl/1-0/"
    # Date of the loaded snapshot; null when the database cannot be reached.
    snapshot_date: date | None = None


class Error(Model):
    detail: str
    source: Source


class Versions(Model):
    api: str
    python: str


class Health(Model):
    status: Literal["ok"]
    versions: Versions
    source: Source


class ProductSummary(Model):
    code: str = Field(min_length=1, max_length=32)
    name: str | None
    brand: str | None
    category_main: str | None
    nutriscore_grade: NutriscoreGrade | None
    nova_group: Literal[1, 2, 3, 4] | None
    image_url: str | None


class SearchResult(ProductSummary):
    match: Literal["barcode", "name", "brand"]


class SearchResponse(Model):
    query: str
    results: list[SearchResult]
    source: Source


class Nutrition(Model):
    energy_kcal_100g: float | None
    sugars_100g: float | None
    salt_100g: float | None
    fat_100g: float | None
    saturated_fat_100g: float | None
    fiber_100g: float | None
    proteins_100g: float | None


class Explainer(Model):
    text: str
    ai_generated: bool


class Additive(Model):
    additive_id: str
    e_number: str | None
    name: str
    function: str | None
    explainer: Explainer | None


class Ingredient(Model):
    ingredient_id: str
    name: str
    rank: int = Field(ge=1)
    explainer: Explainer | None


class Product(ProductSummary):
    category_name: str | None
    category_source: Literal["off_tags", "model"] | None
    completeness: float | None
    nutrition: Nutrition
    additives: list[Additive]
    ingredients: list[Ingredient]
    off_url: str
    in_graph: bool


class ProductResponse(Model):
    product: Product
    source: Source


class Swap(Model):
    product: ProductSummary
    reason: str
    additive_count: int = Field(ge=0)


class SwapsResponse(Model):
    code: str = Field(min_length=1, max_length=32)
    swaps: list[Swap]
    source: Source


class GraphNode(Model):
    id: str
    kind: Literal["Product", "Brand", "Category", "Additive", "Ingredient"]
    name: str
    nutriscore_grade: NutriscoreGrade | None
    detail: str | None


class GraphEdge(Model):
    model_config = ConfigDict(
        json_schema_serialization_defaults_required=True, populate_by_name=True
    )

    from_: str = Field(alias="from", description="Node id.")
    to: str = Field(description="Node id.")
    type: Literal["MADE_BY", "IN", "CONTAINS", "HAS_INGREDIENT", "CHILD_OF"]


class GraphNeighborhood(Model):
    center: str = Field(description="Node id of the product.")
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    truncated: bool
    source: Source


class CountByKey(Model):
    key: str | None
    label: str
    count: int = Field(ge=0)


class GradeCounts(Model):
    a: int
    b: int
    c: int
    d: int
    e: int


class CategoryGrades(Model):
    category_id: str
    name: str
    graded_count: int = Field(ge=0)
    grades: GradeCounts


class CategoryMedian(Model):
    category_id: str
    name: str
    median: float = Field(ge=0)
    product_count: int = Field(ge=0)


class StatsOverview(Model):
    product_count: int
    named_product_count: int
    brand_count: int
    category_count: int
    additive_count: int
    nutriscore: list[CountByKey]
    nova: list[CountByKey]
    categories: list[CountByKey]
    category_sources: list[CountByKey]
    top_additives: list[CountByKey]
    nutriscore_by_category: list[CategoryGrades]
    median_sugars_by_category: list[CategoryMedian]
    source: Source
