# LabelLens: design system

**The idea: the food label, redesigned.** The interface borrows the structure of the US Nutrition Facts panel: heavy black rules that group information, tight condensed type, and numbers set in a column you can scan. Colour appears only when it carries data.

Claude Code builds every screen from the tokens in this file. If a screen needs something this file does not define, add it here first, then use it.

---

## 1. Tokens

### Colour

| Token | Hex | Use |
| --- | --- | --- |
| `page` | `#F4EFE6` | The page: a warm off-white, so labels and panels stand out as white |
| `paper` | `#FFFFFF` | Panels, inputs, labels and text on ink bands |
| `paper-muted` | `#B8B8B8` | Secondary text on ink bands (10.6:1 on `ink`) |
| `ink` | `#000000` | Text, rules, primary buttons |
| `ink-muted` | `#6B6B6B` | Secondary text, axis labels |
| `rule-light` | `#D9D9D9` | Hairline separators inside a group |
| `focus` | `#1A4BFF` | Keyboard focus ring only (5.3:1 on `page`) |
| `focus-inverse` | `#7D9BFF` | Focus ring on ink bands: 8:1 there, where `focus` manages 3.5:1 |

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
- No gradients, no shadows. Depth comes from rules, and from white panels on the warm page.
- Two grounds only: `page` with `ink` text, and ink bands (`ink` ground, `paper` text, `paper-muted` secondary). `ink-muted` on `page` is 4.65:1, checked by `web/app/tokens.test.ts`.
- The Nutri-Score colours may be large (the home page's grade strip), but still only for Nutri-Score data, and always with the letter.

### Type

One family: **Archivo** (variable, with weight and width axes), from Google Fonts via `next/font`.

| Role | Size / line height | Weight | Width | Notes |
| --- | --- | --- | --- | --- |
| Poster | 20.5% of its container / 0.86 | 900 | 62 | The home headline only. Fills the page width: about 70 px on a phone, 230 px at 1280 px |
| Display | 60 / 60 | 900 | 75 | Product name on the product page; home headline on phones and tablets |
| Title | 36 / 40 | 800 | 85 | Page titles, "Nutrition Facts" panel heading |
| Heading | 21 / 26 | 700 | 100 | Section headings |
| Body | 16 / 24 | 400 | 100 | Paragraphs, explainers |
| Data row | 16 / 22 | 500 (label) and 700 (value) | 85 | Label rows; tabular figures on |
| Small | 14 / 20 | 400 | 100 | Captions, footer, citations |

- Turn on tabular figures (`font-variant-numeric: tabular-nums`) wherever numbers line up.
- Sentence case everywhere. No all-caps labels, no letter-spaced eyebrows.
- Body line length under 70 characters.

**Scale on large screens.** Every size in this file is given at the base size (16 px). In code, type, spacing and the heavy and medium rules are in `rem`, so the whole interface grows together when the base does:

| Window width | Base | So Body is |
| --- | --- | --- |
| up to 1599 px | 16 px (100%) | 16 px |
| 1600 to 2199 px | 18 px (112.5%) | 18 px |
| 2200 px and up | 20 px (125%) | 20 px |

Hairlines (`rule-thin`, `rule-hair`), the 2 px panel border, the 2 px radius and the focus ring stay in px: they are lines, not sizes. A reader who sets a larger default font in their browser gets a larger interface too.

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
- Ink bands run the full window width; their content sits on the page width inside them.

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
| Colours | `page`, `paper`, `paper-muted`, `ink`, `ink-muted`, `rule-light`, `focus`, `focus-inverse` (e.g. `text-ink-muted`) |
| Nutri-Score A to E | `grade-a` … `grade-e` |
| Type roles | `type-poster`, `type-display`, `type-title`, `type-heading`, `type-body`, `type-data-label`, `type-data-value`, `type-small` |
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

A poster for the label. The page is warm `page`; the specimen and every panel are white `paper`, like a label stuck on a pack. Below the hero, full-width bands carry the data.

```
┌──────────────────────────────────────────────────────────────┐
│ ▌▌▌ LabelLens        Read a label  Dashboard  Graph  Ask  About│
│                                                              │
│ What's in it?                       (poster, full page width) │
│ ████████████████████████████████████████████ rule-heavy      │
│                                                              │
│ [ Search 985,260 US products ]          ┌ specimen ─────┐    │
│ Name, brand or barcode. Try: …          │ Nutrition     │ 2° │
│ Scan a barcode or photograph the label  │ Facts  [C]    │    │
│                                         │ ▌▌▌▌▌▌▌▌▌▌▌▌  │    │
│ (results appear here)                   └───────────────┘    │
│                                          Next label           │
│▓ 985,260 products · 74% score C or worse · 70% ultra-proc… ▓▓│ ticker (ink)
│ The shelf, graded                                            │
│ ┌─A─┬──B──┬─────C─────┬──────D──────┬─────E─────┐             │
│ │ 9%│ 17% │    22%    │     27%     │    25%    │  grade strip│
│ └───┴─────┴───────────┴─────────────┴───────────┘             │
│ ┌ Read a label ┐ ┌ Ask a question ┐ ┌ Compare two ┐ tiles      │
│▓ How it's measured: 0.98 · 98% · 97% · 184 ms ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│ (ink)
│▓ LabelLens (huge)                         attribution ▓▓▓▓▓▓▓│ footer (ink)
└──────────────────────────────────────────────────────────────┘
```

**The hero.**
- **Poster headline:** "What's in it?" in Poster, filling the page width (it sizes to its container), over `rule-heavy`.
- **Search on the left, specimen on the right** (stacked on phones, search first). The search is unchanged: count in the placeholder from `/stats/overview`, the "Try:" examples, "Scan a barcode or photograph the label".
- **The specimen** is a real product's Nutrition Facts panel, the same component as the product page, printing in on load. Above it: the product's name, brand and grade chip. Under it: the product's real EAN-13 barcode, drawn from its digits, which the site's own scanner can read off the screen. The panel is tilted 2 degrees (a transform, so it is not motion). "Next label" shows the next of three products (A, C and E), and the new one prints in.
- **Typing in the search hides the specimen and everything below the hero,** so results sit right under the box.

**The bands, in order.**
- **Ticker (ink band):** the dashboard's findings as one line of `type-data-value` in `paper`, separated by " · ", scrolling slowly (40 s per loop, transform only). It pauses on hover and focus and stands still under reduced motion. The copy that scrolls in from the right is `aria-hidden`; screen readers get the list once.
- **The shelf, graded:** a full-width strip of the five grade colours, each block as wide as its share of graded US products, with the letter large, the percentage and the count, in the chip's text colour for that grade. On phones it becomes five rows: letter, a bar as long as the share, the percentage. It links to the dashboard. This is where the page's colour comes from, and it is all data.
- **Ways in:** three label panels: read a label from a photo, ask a question, compare two products. Each has a title, one line, and an arrow. The dashboard and the graph follow as text links.
- **How it's measured (ink band):** four numbers in Display, each with a one-line label and a link to its eval report: the agent's fact score, label values read right, MCP tool choice, search p95.
- **Footer (ink band):** see "Footer".

Everything below the hero needs `/stats/overview`; if the API is asleep, the ticker and the strip are left out, never shown empty.

**Scanner.** On devices with a camera, "Scan a barcode" sits on its own line under the "Try:" line, as an underlined text button like the examples, followed by a link, "or photograph the label", to Read a label. It opens a panel (2 px `ink` border, square) right under that line, above the results: the live camera picture at full panel width, one `type-small` line under it that says what is happening ("Point the camera at the barcode. The picture stays on this device."), and a "Cancel" button. A read goes straight to the product page; a barcode the snapshot lacks says so, with links to photograph its label instead and to add the product on Open Food Facts. No scanning animation or overlay, so reduced motion needs nothing special. Focus moves to "Cancel" when the panel opens and back to "Scan a barcode" when it closes; Escape closes it.

### Header and footer

- **Header:** on `page`. A small barcode mark (seven bars) beside the wordmark, then Read a label, Additives, Dashboard, Graph, Ask and About, and "My basket (n)" once the basket has something in it. Below `md` (768 px) it is two lines that never wrap further: the wordmark with the basket count at the right, then Read a label, Additives, Dashboard and Ask; Graph and About are in the footer, which always has every link.
- **Footer:** an ink band. The wordmark large (Display), the links again, and the Open Food Facts attribution (rule 6) in `paper-muted`, its links in `paper`.

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

**High in, low in.** Under every Nutrition Facts panel (product page, label read, home specimen), plain words say which of fat, saturates, sugars and salt are high or low per 100 g (drinks per 100 ml), by the UK's front-of-pack criteria, the only published per-100 g standard. Medium is not shown.

```
│  Nutrition Facts panel           │
│  ████████████████ rule-heavy     │
│  High in sugars                  │  type-data-value, one per line
│  Low in fat · Low in salt        │  type-data-label
│  By the UK front-of-pack         │  type-small ink-muted, with the
│  criteria, per 100 g.            │  source linked
```

- Words only, never colour: colour belongs to Nutri-Score.
- "High in" lines come first and in `type-data-value`; "Low in" lines follow in `type-data-label`.
- A nutrient the label doesn't list gets no flag. Nothing shows when no nutrient is high or low.
- In the comparison table, a high or low value carries the word beside it ("32 g · High").

### Compare

Two products in one label panel, no wider than the reading width (`max-w-measure`), so each value stays close to its label. Reached from a product page ("Compare with another product") or from a swap ("Compare"); the URL is `/compare?codes=A,B`.

```
┌────────────────────────────────────────────────────────────┐
│ Compare                                          (title)   │
│ ┌ panel ───────────────────────────────────────────────┐   │
│ │ ████████████████████████████████████ rule-heavy       │   │
│ │              Cheerios              Honey Nut Cheerios │   │
│ │              General Mills         General Mills      │   │
│ │              [ A ]                 [ C ]              │   │
│ │ ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬ rule-medium      │   │
│ │ Per 100 g                                             │   │
│ │ Energy           376 kcal          393 kcal           │   │
│ │                                    17 kcal more       │   │
│ │ ─ rule-thin between rows, rule-medium between groups  │   │
│ │ ...                                                   │   │
│ │ ▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬ rule-medium      │   │
│ │ Processing       NOVA 1             NOVA 4            │   │
│ │ Additives        1                  4                 │   │
│ │ Ingredients      6                  12                │   │
│ │ ████████████████████████████████████ rule-heavy       │   │
│ └───────────────────────────────────────────────────────┘   │
│ Additives                                       (heading)  │
│  In both · Only in Cheerios · Only in Honey Nut Cheerios   │
└────────────────────────────────────────────────────────────┘
```

- Three columns at every width: row label, then each product. Values are right aligned in tabular figures; at 375 px names and long labels wrap, values do not.
- Under the second product's value, in `type-small` `ink-muted`, its difference from the first ("6 g less", "Same"). Facts only: nothing is called better or worse except by the Nutri-Score grade itself.
- A missing value reads "Not listed", as on the product page, and has no difference.
- With one product picked, the second column is a search box for the other.
- No motion: "the label prints" belongs to the product page.

### Dashboard

A two-column grid of charts, each inside a panel opened by `rule-heavy` with its finding as the heading ("Most US cereals score C or worse"). One chart per question. Charts are black bars and lines; Nutri-Score colours only on Nutri-Score charts.

### Graph explorer

Full width below the header. The title, intro and search sit on the page width, lined up with the header; the graph below them fills the full width, and a panel on the right shows the selected node in label style. Nodes are black dots; the selected product is the only filled shape with its grade colour.

Labels never overlap. A label shows only where it clears every other label, covers no other dot and fits inside the canvas; the most linked nodes are labelled first, and the centre product and the selected node always are. Zooming in reveals more labels, zooming out fewer, and hovering shows any node's name.

### Ask

A single column: the question box, then each agent step as a row in a label-style panel (tool name, what it looked up, row count), then the answer with numbered citations that link to the rows.

### My basket

`/basket`. The products someone is thinking of buying, looked at together. Kept in the browser only (no account), 30 at most. "Add to my basket" sits in the link row on product pages and under a label read that matched a product; the header shows the count once it is above zero.

```
┌────────────────────────────────────────────────────────────┐
│ My basket                                      (title)     │
│ ████████████████████████████████████████████ rule-heavy    │
│ 6 products · 4 ultra-processed · 2 flagged additives       │
│ ┌A┬─B─┬───C───┬────D────┬──E──┐  grade bar, by count       │
│ High in sugars: 3 · High in salt: 2 · High in saturates: 1 │
│                                                            │
│ Product name, brand              [ D ]   Remove            │
│ High in sugars · High in salt                              │
│ Better swap: Product (B), one additive fewer  [ Swap ]     │
│ ─────────────────────────────────────────── rule-hair      │
│ ...                                                        │
│ Additives across the basket       (heading)                │
│ E338 Phosphoric acid · in 2 products · Flagged by OFF      │
│ Share this basket: link                                    │
└────────────────────────────────────────────────────────────┘
```

- **Facts, not a score of the person.** The summary counts grades, processing, flagged additives and high-in flags; it never rates the basket or the shopper.
- **Swap** replaces the item with the top swap (the product page's rule), and the summary updates. The old product can be added back.
- The grade bar is one bar of the five Nutri-Score colours, each as long as its count, the letter on each segment; products with no grade are counted in words.
- **Sharing:** `/basket?codes=…` (barcodes only) opens a read-only copy with "Save as my basket".
- **Empty:** an invitation, with search, scan and read-a-label as the ways to start.

### My preferences

`/preferences`. Someone's own rules, set once and kept in this browser only (no account). Every rule is optional and starts empty: the site never fills in or suggests a value.

```
┌────────────────────────────────────────────────────────────┐
│ My preferences                                   (title)   │
│ ████████████████████████████████████████████ rule-heavy    │
│ Your own rules, checked on every product...      (body)    │
│ Limits per 100 g                     (heading)             │
│ Sugars    [      ] g, at most                              │
│ Salt      [      ] g, at most                              │
│ Saturated fat [  ] g, at most                              │
│ Nutri-Score   [ Any ▾ ]  or better                         │
│ ☐ Not ultra-processed (NOVA 4)                             │
│ Additives to avoid                   (heading)             │
│ [ Find an additive ]  → matches as rows with "Avoid"       │
│ E129 Allura red   Remove                                   │
│ Saved in this browser.  Clear my rules       (small)       │
└────────────────────────────────────────────────────────────┘
```

- Inputs are `panel` boxes like search, one column on the reading width. A change is saved at once; the status line says so.
- **Your rules box** (product page and label read, under the high-in flags): a `rule-thin` above, the heading "Your rules", then one row per rule: the rule in `type-data-label`, the outcome in words on the right in `type-data-value` ("Meets", "Misses", "Not known"), and the product's value in `type-small` under a miss. Words only, no colour and no ticks: colour belongs to Nutri-Score. With no rules set, one `type-small` line links to `/preferences`.
- **Compare** adds a "Your rules" row to the table: "Meets all 4" or "Misses 2", only when rules are set.
- **My basket** adds "n of m meet all your rules" to the summary, and "Misses your rules: sugars, Nutri-Score" under each item that misses one.
- **Wording:** always "your rules", never "recommended", "healthy" or "safe". Missing data is "Not known", never a pass.

### Additive guide

`/additives` and `/additives/[slug]`. What each additive on a US label is, how common it is, and where it turns up. Every additive row elsewhere (product page, label read, basket) links to its guide page.

```
┌────────────────────────────────────────────────────────────┐
│ Additives                                        (title)   │
│ ████████████████████████████████████████████ rule-heavy    │
│ 515 additives on US labels, most common first.   (body)    │
│ [ Find an additive: name or E number ]  ☐ Flagged only     │
│ E330  Citric acid · acidity regulator      100,764         │
│ ─────────────────────────────────────────── rule-hair      │
│ E322  Lecithins · emulsifier                38,120         │
│ ...                                                        │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ E330                                       (type-data)     │
│ Citric acid                                (display)       │
│ Acidity regulator · Flagged by Open Food Facts             │
│ ████████████████████████████████████████████ rule-heavy    │
│ What it is: the explainer, with the AI note    (reading)   │
│                                                            │
│ 100,764        24%                         (type-display)  │
│ US products    of named products                           │
│ ─────────────────────────────────────────── rule-thin      │
│ Used most in              (heading)                        │
│ Sodas            ████████████████  8,210   ink bars        │
│ Candy            ██████████        5,034                   │
│ ─────────────────────────────────────────── rule-thin      │
│ Products that list it     (heading, swap-list rows)        │
└────────────────────────────────────────────────────────────┘
```

- **The list** is one column on the page width: E number in `type-data-value`, the name, its function in `type-small`, the count right-aligned in tabular figures. Typing filters by name or E number at once; "Flagged only" is a checkbox. The count is the order, so no sort control.
- **Flagged** is words, never colour ("Flagged by Open Food Facts"), as everywhere else.
- **Used most in** is a bar per category in `ink`, as long as its count against the first; numbers beside each bar. Colour stays with Nutri-Score.
- **Products that list it** reuses the swap-list rows (name, brand, grade chip), best-ranked first, up to six.
- **Facts only.** The guide says what an additive is, what it does and where it is used, and whether Open Food Facts flags it. It never says an additive is safe or unsafe, or to avoid one.

### Read a label

`/label`. The photo step is a single column on the reading width; the result uses the product page's layout, because it is a product page for a pack LabelLens may not know.

```
┌────────────────────────────────────────────────────────────┐
│ Read a label                                     (title)   │
│ ████████████████████████████████████████████ rule-heavy    │
│ Photograph the ingredients, the nutrition panel, or both.  │
│ ┌ panel ──────────────┐ ┌ panel ──────────────┐            │
│ │ [photo]             │ │ [photo]             │  up to 2   │
│ │ Remove              │ │ Remove              │            │
│ └─────────────────────┘ └─────────────────────┘            │
│ [ Add a photo ]  [ Read the label ]   (button, primary)    │
│ Photos go to Anthropic to be read...          (small)      │
│ Or try a sample: Cereal · Soda · Cookies      (small)      │
├────────────────────────────────────────────────────────────┤
│ Name as read   (display)        │  Nutrition Facts panel    │
│ Brand, category                 │  per 100 g, as on the     │
│ Read by AI from your photo...   │  product page; the        │
│ Additives (n), Ingredients (n)  │  conversion note under it │
│ Looks like X in our data        │                           │
│  └ Compare table: your label vs X                           │
│ Better swaps / Well-graded <category>                       │
└────────────────────────────────────────────────────────────┘
```

- Photo tiles are panels with the photo at full tile width (`object-contain`, square) and a "Remove" text button. On a phone, "Add a photo" opens the camera; on a desktop, a file picker, and a photo can be dropped onto the tiles.
- While it reads, one `type-body` line says so; nothing animates. The result then prints with the product page's motion.
- What was read is labelled as read by AI from the photo, every time. A product match is "Looks like", never "This is". A value the label does not print reads "Not listed".
- A flagged additive says "Flagged by Open Food Facts" in text, as on the MCP card, here and on the product page.
- A sample result says "Recorded example" above it.

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

- Responsive from 375 px to 2560 px (see "Scale on large screens").
- Visible focus ring (`focus`, 2 px, 2 px offset) on every interactive element.
- After a navigation inside the site, focus moves to `<main>`, so the next Tab lands on the new page's first control. `<main>` is not a control, so it shows no ring.
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
