# 0008: The MCP App (phase 6)

Status: accepted. Date: 2026-11-18. Phase 6.

## Public, read-only and unauthenticated, on purpose

**Chosen:** `/mcp` needs no account and no key. Its four tools (`search_products`, `get_product`, `find_swaps`, `explain_additive`) read the same serving tables the website shows, through the same queries.
**Why:**
- Everything it returns is already public on the website and comes from an open database (ODbL), so a login would protect nothing.
- Nothing it does costs money per call: no model call, no embedding, only indexed reads.
- Anyone can add it to Claude by URL, with no OAuth step.
**Rejected:** OAuth (a sign-in flow and a token store for public data), and API keys (friction for a demo, and a secret to leak).

**What follows from it:**
- **No host or origin check** (the SDK's DNS-rebinding protection is off). A rebinding page could only read what anyone can read, the server sets no cookies and holds no session, and Cloud Run routes only its own hostnames.
- **Every text result ends with the ODbL attribution** and the snapshot date, and so does the card.

## Stateless streamable HTTP, on the API it extends

**Chosen:** the official Python SDK (`mcp` 2.3), mounted on the FastAPI app at exactly `/mcp`. Clients on the 2026-07-28 revision need no session at all. `stateless_http` gives older clients the same, so either Cloud Run instance answers any request with no sticky routing. Responses are JSON, not event streams: every tool answers in one response.
**Why:**
- One service, one deploy and one connection pool. The tools are the API's own functions.
- Stateless keeps Cloud Run's "0 to 2 instances" model intact.
**Rejected:** a separate MCP service (a second deploy and pool for four thin tools), and sessions (sticky routing on Cloud Run).

## Rate limit in memory, per client

**Chosen:** 60 requests a minute per client, held in each instance's memory. A client is an IPv4 address or an IPv6 /64, the same as for `/ask`. Over the limit, a 429 with `Retry-After`.
**Why:**
- The tools are cheap reads, so a database write per call (as `/ask` does) would cost more than the abuse it stops.
- Two instances at most make the real ceiling 120 a minute, which Neon handles easily.
**Rejected:** the `/ask` run log (a write per call), and no limit (the spec asks for one, and it caps a runaway client).

## The card: one file, no framework, the design system's tokens

**Chosen:** `get_product` and `find_swaps` link a `ui://` resource under the MCP Apps extension. It is one self-contained HTML file that speaks the host bridge by hand in about 60 lines (`ui/initialize`, tool results, size changes, `ui/open-link`).
- **Looks:** DESIGN.md's tokens, rules and "the label prints" motion, with no motion under reduced motion.
- **Light only:** it stays a printed label on paper, even in a dark host.
- **No product images:** DESIGN.md has no image treatment, and images would widen the CSP and need CC BY-SA credit.
- **Safe with outside data:** product names are data, so the card builds text nodes and never markup.
- **CSP:** it asks for Google Fonts only.
- **Fallback:** every tool also returns readable text, for clients without UI.

**Why:** a build step or a UI framework for one card adds more than it saves, and a hand-written bridge has nothing to update.
**Rejected:**
- The ext-apps browser SDK: a CDN dependency, plus a wider CSP.
- React: a build step for one panel.
- Reusing the web app's components: they need Next.js and Tailwind.

**Checked without Claude:** `scripts/card_preview.py` plays the host (a sandboxed frame under the card's CSP) with real tool results. Checked at 375, 1280 and 1600 px.

## The eval: tool choice from the definitions alone

**Chosen:**
- 30 requests written to sound like real ones, with the expected tool and arguments: 8 search, 8 product, 7 swaps, 5 additive and 2 off-topic.
- The runner reads the tool definitions and server instructions from the server itself and asks Haiku with exactly those.
- A request passes when the first call is the right tool with matching arguments.
- CI runs it when the server, dataset or runner changes. Runs are cached by tool-definition hash, so an unrelated change replays for $0.

**Why Haiku:** the real client in Claude is a larger model, so passing on Haiku is the stricter test.

**What the first run taught:**
- The first run scored 83%: Haiku looked a product up with `get_product` before finding swaps for it.
- The fix was the definitions, not the dataset:
  - `find_swaps` now says it already includes the product and covers "better, healthier or instead".
  - `get_product` points to it.
  - The server instructions say to call it directly.
- After the fix it scored 90%, then 97%. Two more fresh runs scored 97% and 97%, each with a different single miss. The usual miss is the model answering "what does MSG do" from its own knowledge.
- On 30 requests, 29/30 has a 95% interval of 83–99%. That's enough to show the definitions work, but not to rank small wording changes against each other.

**In Claude itself:** the card renders in a Claude conversation for both `get_product` and `find_swaps`, and Claude chains the tools on its own, a search and then the product's card (screenshots in `docs/evidence/phase-6/`).

## Also

- **`serving.additives` gains `flagged`** (OFF's high overexposure risk), so Postgres can answer `explain_additive` and mark flagged additives on the card. Before this, the flag lived only in the dbt mart and the graph.
- **`explain_additive` accepts the abbreviations US labels use:** MSG, BHA, BHT, TBHQ and EDTA. Open Food Facts has no aliases for them.
