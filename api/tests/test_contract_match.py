"""The API's generated OpenAPI schema matches docs/openapi.yaml, field by field.

For every implemented endpoint, the 200 response schema in both documents is walked to the
leaves: the same property names and the same required fields at every object level, and
arrays of the same shape. Nullable wrappers (anyOf with null, type lists) and allOf
composition are unwrapped first, so only the shape is compared, not how it is written.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from api.app.config import Settings
from api.app.main import create_app

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
GENERATED = create_app(Settings(_env_file=None, database_url=None)).openapi()  # pyright: ignore[reportCallIssue]
IMPLEMENTED = [
    ("get", "/health"),
    ("get", "/search"),
    ("get", "/products/{code}"),
    ("get", "/stats/overview"),
    ("get", "/additives"),
    ("get", "/additives/{slug}"),
    ("post", "/label"),
    ("get", "/ready"),
    ("get", "/warm"),
]


def _resolve(doc: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = doc
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def _unwrap(doc: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    node = _resolve(doc, node)
    for key in ("anyOf", "oneOf"):
        if key in node:
            options = [
                _resolve(doc, o) for o in node[key] if _resolve(doc, o).get("type") != "null"
            ]
            if len(options) == 1:
                return _unwrap(doc, options[0])
    if "allOf" in node:
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for part in node["allOf"]:
            part = _unwrap(doc, part)
            merged["properties"].update(part.get("properties", {}))
            merged["required"] += part.get("required", [])
        return merged
    return node


def _kind(node: dict[str, Any]) -> str:
    kind = node.get("type", "object" if "properties" in node else "scalar")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    return kind


def shape(doc: dict[str, Any], node: dict[str, Any], depth: int = 0) -> Any:
    node = _unwrap(doc, node)
    kind = _kind(node)
    if kind == "array":
        return ["array", shape(doc, node.get("items", {}), depth + 1)]
    if kind == "object" and "properties" in node and depth < 8:
        return {
            "required": sorted(node.get("required", [])),
            "properties": {
                name: shape(doc, child, depth + 1)
                for name, child in sorted(node["properties"].items())
            },
        }
    return "object" if kind == "object" else "scalar"


def _ok_schema(doc: dict[str, Any], method: str, path: str) -> dict[str, Any]:
    response = _resolve(doc, doc["paths"][path][method]["responses"]["200"])
    return response["content"]["application/json"]["schema"]


@pytest.mark.parametrize(("method", "path"), IMPLEMENTED)
def test_response_shape_matches_the_contract(method: str, path: str) -> None:
    generated = shape(GENERATED, _ok_schema(GENERATED, method, path))
    contract = shape(CONTRACT, _ok_schema(CONTRACT, method, path))
    assert generated == contract


@pytest.mark.parametrize(("method", "path"), IMPLEMENTED)
def test_error_responses_use_the_contract_error_shape(method: str, path: str) -> None:
    for status, response in CONTRACT["paths"][path][method]["responses"].items():
        if status == "200":
            continue
        contract_schema = _resolve(CONTRACT, response)["content"]["application/json"]["schema"]
        generated_response = GENERATED["paths"][path][method]["responses"].get(status)
        assert generated_response, f"{method.upper()} {path} does not declare {status}"
        generated_schema = generated_response["content"]["application/json"]["schema"]
        assert shape(GENERATED, generated_schema) == shape(CONTRACT, contract_schema)


def test_query_and_path_parameters_match() -> None:
    for method, path in IMPLEMENTED:
        contract_params = {
            _resolve(CONTRACT, p)["name"]
            for p in CONTRACT["paths"][path][method].get("parameters", [])
        }
        generated_params = {
            p["name"] for p in GENERATED["paths"][path][method].get("parameters", [])
        }
        assert generated_params == contract_params, path
