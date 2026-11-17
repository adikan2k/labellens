"""Response models shared across endpoints. Mirrors docs/openapi.yaml."""

from datetime import date
from typing import Literal

from pydantic import BaseModel


class Source(BaseModel):
    """Attribution carried by every response."""

    name: Literal["Open Food Facts"] = "Open Food Facts"
    url: str = "https://world.openfoodfacts.org"
    licence: Literal["ODbL-1.0"] = "ODbL-1.0"
    licence_url: str = "https://opendatacommons.org/licenses/odbl/1-0/"
    # Filled from the loaded snapshot once serving tables exist (phase 2).
    snapshot_date: date | None = None


class Versions(BaseModel):
    api: str
    python: str


class Health(BaseModel):
    status: Literal["ok"]
    versions: Versions
    source: Source
