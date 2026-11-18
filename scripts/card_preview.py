"""Preview the MCP label card without Claude: a local page plays the host.

Calls get_product and find_swaps in-process against a database, then writes a page that frames
the card the way an MCP Apps host does (a sandboxed iframe under the card's declared CSP),
answers its ui/initialize, sends it each tool result and follows its size reports.

    uv run python scripts/card_preview.py --serve 8765
    # then open http://localhost:8765

--database-url defaults to the local Docker database. Nothing is sent anywhere else.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LOCAL_DB = "postgresql://labellens:labellens@localhost:54329/labellens"
OUT = ROOT / "data" / "card-preview"  # data/ is gitignored

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LabelLens card preview</title>
<style>
  body { margin: 0; padding: 16px; background: #FFFFFF; font: 14px/20px system-ui, sans-serif; }
  h2 { font-size: 14px; font-weight: 600; margin: 16px 0 8px; color: #6B6B6B; }
  iframe { display: block; width: 100%; border: 0; height: 200px; }
</style></head>
<body>
<p>A stand-in host: each frame below is the card as an MCP Apps host would load it.</p>
<div id="frames"></div>
<script>
const CARD = __CARD__;
const CSP = __CSP__;
const RESULTS = __RESULTS__;
const frames = document.getElementById("frames");
const byWindow = new Map();
for (const [title, result] of RESULTS) {
  const h = document.createElement("h2");
  h.textContent = title;
  const iframe = document.createElement("iframe");
  iframe.setAttribute("sandbox", "allow-scripts");
  iframe.title = title;
  const policy = `<meta http-equiv="Content-Security-Policy" content="${CSP}">`;
  iframe.srcdoc = CARD.replace("<head>", "<head>" + policy);
  frames.append(h, iframe);
  // Known before the card runs: it says ui/initialize before the frame's load event.
  byWindow.set(iframe.contentWindow, { iframe, result });
}
window.addEventListener("message", (event) => {
  const entry = byWindow.get(event.source);
  const msg = event.data;
  if (!entry || !msg || msg.jsonrpc !== "2.0") return;
  const reply = (body) => event.source.postMessage({ jsonrpc: "2.0", ...body }, "*");
  if (msg.method === "ui/initialize") {
    reply({ id: msg.id, result: { protocolVersion: "2026-01-26",
      hostInfo: { name: "labellens-preview", version: "1" }, hostCapabilities: { openLinks: {} },
      hostContext: { theme: "light", displayMode: "inline", locale: "en-US" } } });
  } else if (msg.method === "ui/notifications/initialized") {
    reply({ method: "ui/notifications/tool-input", params: { arguments: {} } });
    setTimeout(() => reply({ method: "ui/notifications/tool-result", params: entry.result }), 150);
  } else if (msg.method === "ui/notifications/size-changed") {
    entry.iframe.style.height = `${msg.params.height}px`;
  } else if (msg.method === "ui/open-link") {
    window.open(msg.params.url, "_blank", "noopener");
    reply({ id: msg.id, result: {} });
  }
});
</script>
</body></html>
"""


def _js(value: Any) -> str:
    return json.dumps(value).replace("</", "<\\/")


def _csp(hosts: list[str]) -> str:
    """The policy a host builds from the card's _meta.ui.csp (the spec's defaults plus hosts)."""
    allowed = " ".join(hosts)
    return (
        "default-src 'none'; script-src 'unsafe-inline'; "
        f"style-src 'unsafe-inline' {allowed}; font-src {allowed}; img-src data:; "
        "connect-src 'none'"
    )


async def _results(database_url: str, calls: list[tuple[str, str, dict[str, Any]]]) -> list[Any]:
    from mcp import Client

    from api.app.db import Database
    from api.app.mcp.server import create_mcp

    db = Database.open(database_url, timeout=8)
    try:
        server = create_mcp(lambda: db, "https://labellens-beige.vercel.app").server
        out = []
        async with Client(server) as client:
            for title, tool, args in calls:
                result = await client.call_tool(tool, args)
                out.append([title, result.model_dump(mode="json", by_alias=True)])
        return out
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preview the MCP label card locally.")
    parser.add_argument("--database-url", default=LOCAL_DB)
    parser.add_argument("--code", default="0016000123991", help="product for get_product")
    parser.add_argument("--swaps-code", default="0028400516464", help="product for find_swaps")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--serve", type=int, help="serve the page on this port")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    import anyio

    from api.app.mcp.server import CARD_HTML, FONT_HOSTS

    calls = [
        ("get_product", "get_product", {"code": args.code}),
        ("find_swaps", "find_swaps", {"code": args.swaps_code}),
        ("get_product, unknown barcode", "get_product", {"code": "0000000000000"}),
    ]
    results = anyio.run(_results, args.database_url, calls)
    page = (
        PAGE.replace("__CARD__", _js(CARD_HTML))
        .replace("__CSP__", _js(_csp(FONT_HOSTS)))
        .replace("__RESULTS__", _js(results))
    )
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "index.html").write_text(page, "utf-8", newline="\n")
    print(f"Wrote {args.out / 'index.html'}")
    if args.serve:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(args.out))
        print(f"Serving http://localhost:{args.serve} (Ctrl+C to stop)")
        http.server.ThreadingHTTPServer(("127.0.0.1", args.serve), handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
