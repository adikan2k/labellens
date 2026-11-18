"""A stand-in for Voyage's embeddings API: httpx.MockTransport with deterministic vectors.

Each text becomes a hashed bag of its words, normalised, so texts that share words are close
under cosine distance. That is enough for retrieval tests to be meaningful without a network.
"""

from __future__ import annotations

import hashlib
import json
import math
import re

import httpx

from api.app.embeddings import DIMENSION, Voyage


def fake_vector(text: str) -> list[float]:
    vector = [0.0] * DIMENSION
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        digest = hashlib.sha256(word.encode()).digest()
        vector[int.from_bytes(digest[:4], "big") % DIMENSION] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class FakeVoyageServer:
    """Records each request body; answers like Voyage, or with `status` when set."""

    def __init__(self, status: int = 200):
        self.status = status
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append({**body, "authorization": request.headers.get("authorization")})
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "fake failure"})
        texts = body["input"]
        data = [
            {"object": "embedding", "embedding": fake_vector(t), "index": i}
            for i, t in enumerate(texts)
        ][::-1]  # out of order on purpose: the client must sort by index
        tokens = sum(len(t.split()) for t in texts)
        return httpx.Response(200, json={"data": data, "usage": {"total_tokens": tokens}})

    def client(self, model: str = "voyage-4-lite", key: str | None = "test-key") -> Voyage:
        return Voyage(key, model, client=httpx.Client(transport=httpx.MockTransport(self.handler)))
