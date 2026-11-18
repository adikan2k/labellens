"""Production smoke test: read-only checks against the deployed API and web app.

    uv run python scripts/smoke.py
    uv run python scripts/smoke.py --api http://localhost:8000 --web http://localhost:3000
    uv run python scripts/smoke.py --expect-unknown-404   # once the web 404 page ships

Prints one line per check and exits 1 on any failure. Nothing here writes data or calls a
model: /ask gets a two-character question, which the API rejects with 422 before any model
runs. MCP requests use the stateless 2026-07-28 protocol (headers plus params._meta).
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TextIO

import httpx

API = "https://labellens-api-1036759996795.us-east4.run.app"
WEB = "https://labellens-beige.vercel.app"
CODE = "0016000123991"  # Lucky Charms: in the serving tables, the graph and the swaps
# Nacho Cheese Doritos: has swaps. Lucky Charms may have none, which is a valid answer.
SWAP_CODE = "0028400516464"
UNKNOWN = "0000000000000"
PAGES = (
    "/",
    "/dashboard",
    "/graph",
    "/ask",
    "/about",
    f"/product/{CODE}",
    f"/compare?codes={CODE},{SWAP_CODE}",
)
MCP_VERSION = "2026-07-28"
MCP_TOOLS = {"search_products", "get_product", "find_swaps", "explain_additive"}
TIMEOUT = 30.0  # Cloud Run scales to zero; a cold start takes a few seconds


class Failed(Exception):
    pass


@dataclass(frozen=True)
class Result:
    name: str
    ok: bool
    detail: str
    seconds: float


def expect(condition: object, message: str) -> None:
    if not condition:
        raise Failed(message)


def _json(response: httpx.Response, status: int = 200) -> Any:
    expect(
        response.status_code == status,
        f"HTTP {response.status_code}, expected {status}: {response.text[:200]}",
    )
    try:
        return response.json()
    except ValueError as exc:
        raise Failed(f"not JSON: {response.text[:200]}") from exc


def mcp_request(client: httpx.Client, api: str, method: str, params: dict[str, Any]) -> Any:
    """One JSON-RPC request to /mcp as a stateless 2026-07-28 client; returns `result`."""
    meta = {
        "io.modelcontextprotocol/protocolVersion": MCP_VERSION,
        "io.modelcontextprotocol/clientCapabilities": {},
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": MCP_VERSION,
        "Mcp-Method": method,
    }
    if "name" in params:  # tools/call names its tool in a header too, and they must match
        headers["Mcp-Name"] = params["name"]
    response = client.post(
        f"{api}/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": {**params, "_meta": meta}},
    )
    body = _json(response)
    expect("error" not in body, f"JSON-RPC error: {body.get('error')}")
    return body["result"]


# Each check takes the client and the two base URLs and returns a short detail line.
CheckFn = Callable[[httpx.Client, str, str], str]


def health(c: httpx.Client, api: str, web: str) -> str:
    body = _json(c.get(f"{api}/health"))
    expect(body.get("status") == "ok", f"status is {body.get('status')!r}")
    return f"api {body['versions']['api']}, snapshot {body['source'].get('snapshot_date')}"


def search(c: httpx.Client, api: str, web: str) -> str:
    body = _json(c.get(f"{api}/search", params={"q": "cheerios"}))
    results = body.get("results") or []
    expect(results, "no results for 'cheerios'")
    expect(
        any("cheerios" in (r.get("name") or "").lower() for r in results),
        "no result is named Cheerios",
    )
    return f"{len(results)} results"


def product(c: httpx.Client, api: str, web: str) -> str:
    body = _json(c.get(f"{api}/products/{CODE}"))
    found = body.get("product") or {}
    expect(found.get("code") == CODE, f"code is {found.get('code')!r}")
    return f"{found.get('name')}, Nutri-Score {found.get('nutriscore_grade')}"


def swaps_of(code: str, *, required: bool) -> CheckFn:
    def check(c: httpx.Client, api: str, web: str) -> str:
        body = _json(c.get(f"{api}/products/{code}/swaps"))
        expect(body.get("code") == code, f"code is {body.get('code')!r}")
        found = body.get("swaps")
        expect(isinstance(found, list), "swaps is not a list")
        expect(found or not required, "no swaps")
        return f"{len(found)} swaps"

    return check


def graph(c: httpx.Client, api: str, web: str) -> str:
    body = _json(c.get(f"{api}/graph/neighborhood", params={"code": CODE, "depth": 1}))
    expect(body.get("center") == f"Product:{CODE}", f"center is {body.get('center')!r}")
    expect(len(body.get("nodes") or []) > 1, "no neighbours")
    return f"{len(body['nodes'])} nodes, {len(body.get('edges') or [])} edges"


def ask_rejects_short(c: httpx.Client, api: str, web: str) -> str:
    response = c.post(f"{api}/ask", json={"question": "hi"})
    _json(response, 422)
    return "422 before any model call"


def mcp_tools(c: httpx.Client, api: str, web: str) -> str:
    names = {t["name"] for t in mcp_request(c, api, "tools/list", {}).get("tools", [])}
    expect(names == MCP_TOOLS, f"tools are {sorted(names)}")
    return f"{len(names)} tools"


def mcp_get_product(c: httpx.Client, api: str, web: str) -> str:
    params = {"name": "get_product", "arguments": {"code": CODE}}
    result = mcp_request(c, api, "tools/call", params)
    expect(not result.get("isError"), f"tool error: {result.get('content')}")
    found = (result.get("structuredContent") or {}).get("product") or {}
    expect(found.get("code") == CODE, f"product code is {found.get('code')!r}")
    return str(found.get("name"))


def page(path: str) -> CheckFn:
    def check(c: httpx.Client, api: str, web: str) -> str:
        response = c.get(f"{web}{path}")
        expect(response.status_code == 200, f"HTTP {response.status_code}")
        # Rule 6: every page keeps the Open Food Facts attribution.
        expect("Open Food Facts" in response.text, "no Open Food Facts attribution")
        return f"{len(response.content):,} bytes"

    return check


def unknown_product(c: httpx.Client, api: str, web: str) -> str:
    response = c.get(f"{web}/product/{UNKNOWN}")
    expect(response.status_code == 404, f"HTTP {response.status_code}, expected 404")
    return "404"


def checks(expect_unknown_404: bool) -> list[tuple[str, CheckFn]]:
    found: list[tuple[str, CheckFn]] = [
        ("api /health", health),
        ("api /search?q=cheerios", search),
        (f"api /products/{CODE}", product),
        (f"api /products/{CODE}/swaps", swaps_of(CODE, required=False)),
        (f"api /products/{SWAP_CODE}/swaps", swaps_of(SWAP_CODE, required=True)),
        ("api /graph/neighborhood", graph),
        ("api POST /ask (too short)", ask_rejects_short),
        ("mcp tools/list", mcp_tools),
        ("mcp tools/call get_product", mcp_get_product),
    ]
    found += [(f"web {path}", page(path)) for path in PAGES]
    if expect_unknown_404:
        found.append((f"web /product/{UNKNOWN} (unknown)", unknown_product))
    return found


def run(
    api: str,
    web: str,
    *,
    expect_unknown_404: bool = False,
    out: TextIO | None = None,
    timeout: float = TIMEOUT,
) -> list[Result]:
    out = out or sys.stdout
    api, web = api.rstrip("/"), web.rstrip("/")
    results: list[Result] = []
    headers = {"User-Agent": "labellens-smoke/1"}
    with httpx.Client(timeout=timeout, follow_redirects=True, headers=headers) as client:
        for name, check in checks(expect_unknown_404):
            started = time.perf_counter()
            try:
                result = Result(name, True, check(client, api, web), 0.0)
            except Failed as exc:
                result = Result(name, False, str(exc), 0.0)
            except (httpx.HTTPError, KeyError, TypeError) as exc:
                result = Result(name, False, f"{type(exc).__name__}: {exc}", 0.0)
            result = Result(result.name, result.ok, result.detail, time.perf_counter() - started)
            results.append(result)
            mark = "ok  " if result.ok else "FAIL"
            line = f"{mark} {name:<38} {result.seconds:5.2f}s  {result.detail}"
            print(line, file=out, flush=True)
    failed = sum(not r.ok for r in results)
    print(f"{len(results) - failed}/{len(results)} checks passed.", file=out)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only checks against production.")
    parser.add_argument("--api", default=API, help=f"API base URL (default {API})")
    parser.add_argument("--web", default=WEB, help=f"web base URL (default {WEB})")
    parser.add_argument(
        "--expect-unknown-404",
        action="store_true",
        help="also require /product/<unknown barcode> to answer 404",
    )
    args = parser.parse_args(argv)
    results = run(args.api, args.web, expect_unknown_404=args.expect_unknown_404)
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
