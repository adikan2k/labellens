# LabelLens: design system

**The idea: the food label, redesigned.** The interface borrows the structure of the US Nutrition Facts panel: heavy black rules that group information, tight condensed type, and numbers set in a column you can scan. Colour appears only when it carries data.

Claude Code builds every screen from the tokens in this file. If a screen needs something this file does not define, add it here first, then use it.

---

## 1. Tokens

### Colour

| Token | Hex | Use |
| --- | --- | --- |
| `paper` | `#FFFFFF` | Page and panel background |
| `ink` | `#000000` | Text, rules, primary buttons |
| `ink-muted` | `#6B6B6B` | Secondary text, axis labels |
| `rule-light` | `#D9D9D9` | Hairline separators inside a group |
| `focus` | `#1A4BFF` | Keyboard focus ring only |

**Data colours (Nutri-Score scale, used only for Nutri-Score data)**

| Grade | Hex |
| --- | --- |
| A | `#038141` |
| B | `#85BB2F` |
| C | `#FECB02` |
| D | `#EE8100` |
| E | `#E63E11` |

Rules for colour:

- Never use a Nutri-Score colour for anything except a Nutri-Score grade.
- Never show a grade by colour alone; the letter is always present.
- Text on grade chips: white on A; black on B, C, D and E. Checked 2026-11-17 against WCAG AA (4.5:1): white on A is 5.0:1, black on B 9.1, C 13.8, D 7.8, E 5.1. White on D (2.7) and E (4.2) fails, so the earlier "white on D and E" was changed. `web/components/label/grade-chip.test.tsx` recomputes these from the tokens.
- No gradients, no tinted backgrounds, no shadows. Depth comes from rules.

### Type

One family: **Archivo** (variable, with weight and width axes), from Google Fonts via `next/font`.

| Role | Size / line height | Weight | Width | Notes |
| --- | --- | --- | --- | --- |
| Display | 60 / 60 | 900 | 75 | Product name on the product page; home headline |
| Title | 36 / 40 | 800 | 85 | Page titles, "Nutrition Facts" panel heading |
| Heading | 21 / 26 | 700 | 100 | Section headings |
| Body | 16 / 24 | 400 | 100 | Paragraphs, explainers |
| Data row | 16 / 22 | 500 (label) and 700 (value) | 85 | Label rows; tabular figures on |
| Small | 14 / 20 | 400 | 100 | Captions, footer, citations |

- Turn on tabular figures (`font-variant-numeric: tabular-nums`) wherever numbers line up.
- Sentence case everywhere. No all-caps labels, no letter-spaced eyebrows.
- Body line length under 70 characters.

### Rules (the signature structural device)

| Token | Thickness | Use |
| --- | --- | --- |
| `rule-heavy` | 10 px | Opens and closes a panel |
| `rule-medium` | 5 px | Separates major groups inside a panel |
| `rule-thin` | 1 px, `ink` | Separates rows in a group |
| `rule-hair` | 1 px, `rule-light` | Separates items in a list outside panels |

Rules are structure, never decoration. If a rule does not separate two groups of information, delete it.

### Space, shape, layers

- Spacing scale on a 4 px base: 4, 8, 12, 16, 24, 32, 48, 64, 96.
- Corner radius: 0 for panels and inputs (labels are rectangles); 2 px for buttons and chips.
- One border style for panels: 2 px `ink`.
- Layers: page, panel, popover. Popovers use a 2 px `ink` border, not a shadow.

### Motion

| Token | Value |
| --- | --- |
| `ease-out` | `cubic-bezier(0.2, 0, 0, 1)` |
| `ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` |
| `dur-fast` | 120 ms |
| `dur-base` | 240 ms |
| `dur-slow` | 420 ms |

Animate only `transform`, `opacity` and `clip-path`. Hold 60 frames a second on a mid-range laptop.

### Token names in code

`web/app/globals.css` defines these tokens and clears Tailwind's defaults, so nothing else is available.

| In this file | In code |
| --- | --- |
| Colours | `paper`, `ink`, `ink-muted`, `rule-light`, `focus` (e.g. `text-ink-muted`) |
| Nutri-Score A to E | `grade-a` … `grade-e` |
| Type roles | `type-display`, `type-title`, `type-heading`, `type-body`, `type-data-label`, `type-data-value`, `type-small` |
| Rules | `rule-heavy`, `rule-medium`, `rule-thin`, `rule-hair` (block elements, so they can scale in) |
| Spacing 4 … 96 px | `1`, `2`, `3`, `4`, `6`, `8`, `12`, `16`, `24` (e.g. `p-4` is 16 px) |
| Radius 2 px | `rounded-control`; panels and inputs use `rounded-none` |
| Panel border | `panel` |
| Body line length | `max-w-measure` (68ch) |
| Page width (header, footer, product page, dashboard) | `max-w-page` (72rem) |
| Motion | `ease-out`, `ease-in-out`, `--dur-fast`, `--dur-base`, `--dur-slow` |

---

## 2. Layout

The site is a single centred column for reading pages and a two-column split for the product page. Content is left aligned. Numbers are right aligned in data rows.

### Home

The search box is the hero. No marketing section above it.

```
┌────────────────────────────────────────────────────────────┐
│ LabelLens                              Dashboard  Graph  Ask│
│                                                            │
│                                                            │
│   What's in it?                                (display)   │
│   ████████████████████████████████████████  (rule-heavy)   │
│   [ Search {count} US products by name, brand or barcode ] │
│   ─────────────────────────────────────────────────────    │
│   Try: Cheerios, Oreo, Coca-Cola                (small)    │
│                                                            │
│   ┌ live result list, one label row per product ───────┐   │
│   │ Product name                      Brand      [ B ] │   │
│   └────────────────────────────────────────────────────┘   │
│                                                            │
│ Contains data from Open Food Facts, available under ODbL.  │
└────────────────────────────────────────────────────────────┘
```

The product count in the placeholder comes from `/stats/overview`, never hard-coded.

### Product page

```
┌──────────────────────────┬─────────────────────────────────┐
│ Product name   (display) │  Nutrition Facts panel          │
│ Brand, category          │  ███████████████ rule-heavy     │
│                          │  Energy           210 kcal      │
│ Nutri-Score [ B ]        │  ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬ rule-medium     │
│ Processing: NOVA 4       │  Fat               8 g          │
│                          │  ─ rule-thin                    │
│ Additives (3)            │  Sugars           12 g          │
│  E330 Citric acid   ⌄    │  ...                            │
│                          │  ███████████████ rule-heavy     │
│ Better swaps             │                                 │
│  ▸ Product   [ A ]       │  (panel is sticky on desktop)   │
│    Same category, A not B│                                 │
└──────────────────────────┴─────────────────────────────────┘
```

On phones the panel moves under the name, and swaps follow it.

### Dashboard

A two-column grid of charts, each inside a panel opened by `rule-heavy` with its finding as the heading ("Most US cereals score C or worse"). One chart per question. Charts are black bars and lines; Nutri-Score colours only on Nutri-Score charts.

### Graph explorer

Full width below the header. The graph fills the space; a panel on the right shows the selected node in label style. Nodes are black dots; the selected product is the only filled shape with its grade colour.

### Ask

A single column: the question box, then each agent step as a row in a label-style panel (tool name, what it looked up, row count), then the answer with numbered citations that link to the rows.

### MCP card (inside Claude)

One panel that fills the host's frame (Claude draws the widget at the conversation's width), drawn by `api/app/mcp/card.html` in the host's sandboxed frame. It uses the tokens above and no others.
- **Product:** name (heading), brand and category, the large grade chip with the NOVA group, a compact Nutrition Facts block per 100 g with the same rule rhythm as the product page, and the additives. A flagged additive says "Flagged by Open Food Facts" in text, never by colour alone.
- **Swaps:** "Better swaps for" the product, then one row per swap: name, brand, reason and its grade chip. A row opens the swap's page.
- **Footer:** "Open in LabelLens", then the ODbL attribution.
- **Always light.** The card is a printed label, so it stays paper and ink in a dark host, inside its own 2 px border.
- **No product images:** this section has no image treatment yet.
- **Motion:** the label prints once per view; an error card simply appears.

---

## 3. Signature motion: the label prints

This is the one memorable moment. Everything else is quiet.

When a product page opens, its Nutrition Facts panel assembles like a label coming off a printer:

1. The top `rule-heavy` draws left to right (`scaleX` 0 → 1, origin left, `dur-base`, `ease-out`).
2. Each data row wipes in from the left with `clip-path: inset(0 100% 0 0)` → `inset(0 0 0 0)`, 30 ms apart, `dur-base`.
3. Each `rule-medium` draws as its group finishes.
4. The bottom `rule-heavy` draws.
5. The Nutri-Score chip settles last: scale 1.06 → 1, `dur-slow`, `ease-out`.

The whole sequence takes under 900 ms. It runs once per page view, never on scroll.

**Supporting motion (answers an action)**

- Search result → product page: a View Transition morphs the result row's name and grade chip into their places on the product page.
- Additive rows expand on click with a height animation (`dur-base`).
- Graph: on selection, the camera eases to the node (`dur-slow`); new neighbours fade in.
- Dashboard bars grow from zero once, the first time each chart enters the viewport.

**Never**

- Fade-and-slide-up on every section.
- Hover animations on every card.
- Number counters that tick up.
- Scroll hijacking or parallax.

**Reduced motion.** With `prefers-reduced-motion: reduce`, the label appears complete, View Transitions are replaced by an instant swap, and nothing moves on its own.

**Tools.** Motion for component and layout animation; the browser View Transitions API for page morphs; Sigma.js (WebGL) for the graph. Add GSAP only if the label sequence needs a timeline that Motion cannot express.

---

## 4. Writing

- Name things by what the shopper sees: "Additives", "Better swaps", "Ask a question".
- Buttons say what happens: "Find swaps", "Show steps", "Open in Open Food Facts".
- Empty search: "No products match. Try a brand name or scan the barcode number."
- Missing data: "Open Food Facts has no sugar value for this product." Never show a blank cell.
- Errors say what failed and what to do: "Search is waking up. Try again in a few seconds."
- AI-generated explainers carry a small note: "Written by AI from Open Food Facts data."

---

## 5. Quality floor

- Responsive from 375 px to 1600 px.
- Visible focus ring (`focus`, 2 px, 2 px offset) on every interactive element.
- All text meets WCAG AA contrast.
- Every chart has a text alternative: its heading states the finding, and the data is available as a table on request.
- Lighthouse performance 90 or better on the home and product pages.

---

## 6. References

Save screenshots to `docs/design/refs/` before building any page:

- A photo of a real Nutrition Facts label from your kitchen. This is the main reference.
- Causal (https://causal.so/): a quiet white page and a tiny navigation bar.
- Hellomatik (https://hellomatik.com/): the real product interface as the hero.
- BehaviorAI (https://www.behaviorai.eu): one large, confident sans-serif headline.

Take from them their restraint, not their components.

---

## 7. Design review notes

Checked against the looks that mark a site as generated:

- Thick black rules and zero radius sit close to the "broadsheet" default. They stay because they come from the subject: the Nutrition Facts panel is built from exactly these rules. To keep it from reading as a newspaper, the rules are heavy bars at three weights, not hairlines, and the layout is a label-width panel, not dense columns.
- No monospace for data. Archivo condensed with tabular figures does that job, as on a real label.
- No accent colour. The only colour is the Nutri-Score scale, and only where it is data.
- The hero is the search box itself, not a headline with stat counters.

Process for every page: build it with real data, screenshot it at 375, 1280 and 1600 px, compare it with the references, fix, and only then move on.
