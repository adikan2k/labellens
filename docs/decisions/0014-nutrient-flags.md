# 0014: High in, low in

Status: accepted. Date: 2026-11-18.

A Nutrition Facts panel gives the grams but not what they mean. Someone reading "22 g sugars" can't tell whether that's a lot. A published threshold can tell them, as a fact, without LabelLens saying what to eat.

## Chosen: the UK front-of-pack criteria, in words

- **The standard:** the UK's front-of-pack criteria for fat, saturates, sugars and salt, per 100 g for food and per 100 ml for drinks. It's the only published per-100 g standard. The figures were taken from the official tables (Annex D of the Scottish Government's "Supporting Healthy Choices", which repeats the Department of Health guide), not from memory, and the source is linked beside the flags.
- **Low and high only:** low is at or under the low figure, and high is over the high figure. Medium isn't shown, because a line saying "medium in fat" adds noise and no information.
- **Words, not colour:** "High in sugars", "Low in salt". Colour stays reserved for Nutri-Score (DESIGN.md), so the red and green of the UK traffic lights aren't used. High lines come first.
- **Drinks by category:** sodas, juices, water/coffee/tea and milk use the drink thresholds, and the panel says so. Everything else counts as food.
- **Where they show:** under every Nutrition Facts panel (product page, label read, home specimen), beside each value in the comparison table, and counted in the basket.
- **One pure function** (`web/lib/thresholds.ts`), so every page gives the same answer and the boundaries are tested in one place.

**Rejected:**
- **US % Daily Value bands** (5% low, 20% high): they're per serving, and serving sizes are often missing or chosen by the maker, so two products can't be compared fairly.
- **Traffic-light colours:** they would compete with the Nutri-Score colours and break the rule that colour only ever means a grade.
- **The per-portion criteria** (for portions over 100 g, or 150 ml for drinks): the site works per 100 g, and the portion is often unknown.
- **Spotting drinks by unit or name** ("ml" in the quantity, "drink" in the name): too often wrong. The category is already cleaned by the pipeline.
- **Showing medium:** it's most products, so it would bury the high and low lines.

## Checked

- The published figures, every boundary (exactly at the low and high figures), drinks against foods, missing values and rendering: `web/lib/thresholds.test.tsx`.
- The compare table's flags: `web/components/compare/compare.test.tsx`.
- Screenshots of a cola (drink thresholds) at 375 and 1280 px, and the comparison table at 1280 px: `docs/design/flags/`.
- The same PR fixed the label reader listing a matched additive such as "tocopherols (vitamin E)" as having no entry (`api/tests/test_label.py`).
