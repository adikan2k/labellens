"""docs/openapi.yaml covers SPEC section 6, and the API's models agree with it."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from api.app.main import app
from api.app.schemas import Health, Source

SPEC_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.yaml"
SPEC: dict[str, Any] = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))

EXPECTED_OPERATIONS = [
    ("get", "/health"),
    ("get", "/search"),
    ("get", "/products/{code}"),
    ("get", "/products/{code}/swaps"),
    ("get", "/stats/overview"),
    ("get", "/graph/neighborhood"),
    ("post", "/ask"),
    ("post", "/mcp"),
]


def _resolve(node: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in node:
        target: Any = SPEC
        for part in node["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        node = target
    return node


def _required(schema: dict[str, Any]) -> set[str]:
    schema = _resolve(schema)
    names = set(schema.get("required", []))
    for part in schema.get("allOf", []):
        names |= _required(part)
    return names


def _json_responses() -> list[tuple[str, str, str, dict[str, Any]]]:
    found = []
    for path, item in SPEC["paths"].items():
        for method, operation in item.items():
            for status, response in operation["responses"].items():
                content = _resolve(response).get("content", {})
                if "application/json" in content:
                    found.append((method, path, status, content["application/json"]["schema"]))
    return found


def test_spec_is_openapi_3_1() -> None:
    assert SPEC["openapi"].startswith("3.1")


@pytest.mark.parametrize(("method", "path"), EXPECTED_OPERATIONS)
def test_every_spec_endpoint_is_in_the_contract(method: str, path: str) -> None:
    assert method in SPEC["paths"].get(path, {}), f"{method.upper()} {path} missing"


def test_no_undocumented_operations() -> None:
    documented = {(m, p) for p, item in SPEC["paths"].items() for m in item}
    assert documented == set(EXPECTED_OPERATIONS)


def test_every_json_response_requires_source() -> None:
    responses = _json_responses()
    assert len(responses) >= 10
    missing = [
        f"{m.upper()} {p} {s}" for m, p, s, schema in responses if "source" not in _required(schema)
    ]
    assert missing == []


def test_ask_answer_requires_source() -> None:
    assert "source" in _required({"$ref": "#/components/schemas/AskAnswer"})


def test_source_schema_matches_the_api_model() -> None:
    spec_source = SPEC["components"]["schemas"]["Source"]
    assert set(spec_source["properties"]) == set(Source.model_fields)
    assert set(spec_source["required"]) == set(Source.model_fields)


def test_health_schema_matches_the_api_model() -> None:
    spec_health = SPEC["components"]["schemas"]["Health"]
    assert set(spec_health["properties"]) == set(Health.model_fields)


def test_implemented_routes_are_in_the_contract() -> None:
    implemented = {
        (method.lower(), route.path)  # type: ignore[attr-defined]
        for route in app.routes
        if getattr(route, "include_in_schema", False)
        for method in route.methods  # type: ignore[attr-defined]
    }
    documented = {(m, p) for p, item in SPEC["paths"].items() for m in item}
    assert implemented <= documented


def test_additive_carries_number_and_function() -> None:
    additive = SPEC["components"]["schemas"]["Additive"]
    assert {"e_number", "function"} <= set(additive["required"])


def test_stats_overview_has_dashboard_figures() -> None:
    stats = SPEC["components"]["schemas"]["StatsOverview"]
    for field in ("named_product_count", "nutriscore_by_category", "median_sugars_by_category"):
        assert field in stats["required"]
        assert field in stats["properties"]
