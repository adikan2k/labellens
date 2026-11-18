"""Voyage AI embeddings (decision 0001): the explainers once, and each question at ask time.

The REST API is called directly with httpx: POST /v1/embeddings with up to 1,000 texts.
`input_type` is "document" for the explainers and "query" for questions, which is how Voyage
expects retrieval pairs. The model and its price live in api/app/config.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import httpx

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
DIMENSION = 1024  # voyage-4-lite's default; the pgvector column is vector(1024)
MAX_BATCH = 1000


class EmbeddingsUnavailable(RuntimeError):
    """No key configured, or Voyage refused or failed the request."""


@dataclass
class Embedded:
    vectors: list[list[float]]
    tokens: int


class Voyage:
    def __init__(self, api_key: str | None, model: str, client: httpx.Client | None = None):
        self.api_key = api_key
        self.model = model
        self.client = client or httpx.Client(timeout=20.0)

    def embed(self, texts: Sequence[str], input_type: Literal["query", "document"]) -> Embedded:
        if not self.api_key:
            raise EmbeddingsUnavailable("EMBEDDINGS_API_KEY is not set")
        if not texts:
            return Embedded([], 0)
        if len(texts) > MAX_BATCH:
            raise ValueError(f"at most {MAX_BATCH} texts per request")
        try:
            response = self.client.post(
                VOYAGE_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "input": list(texts),
                    "model": self.model,
                    "input_type": input_type,
                    "output_dimension": DIMENSION,
                },
            )
        except httpx.HTTPError as error:
            raise EmbeddingsUnavailable(f"Voyage request failed: {error}") from error
        if response.status_code != 200:
            detail = _detail(response)
            raise EmbeddingsUnavailable(f"Voyage answered {response.status_code}: {detail}")
        body = response.json()
        data = sorted(body["data"], key=lambda d: d["index"])  # by input position
        vectors = [d["embedding"] for d in data]
        if len(vectors) != len(texts) or any(len(v) != DIMENSION for v in vectors):
            raise EmbeddingsUnavailable("Voyage returned the wrong number or size of vectors")
        return Embedded(vectors, int(body.get("usage", {}).get("total_tokens", 0)))


def _detail(response: httpx.Response) -> str:
    try:
        body: Any = response.json()
    except ValueError:
        return response.text[:200]
    return str(body.get("detail", body))[:200] if isinstance(body, dict) else str(body)[:200]


def vector_literal(vector: Sequence[float]) -> str:
    """pgvector's text form: '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{x:.7g}" for x in vector) + "]"
