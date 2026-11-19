# 0013: My preferences

Status: accepted. Date: 2026-11-18.

People asked for help planning what they eat. A diet plan would mean telling someone what to eat, which LabelLens doesn't do. What it can do is check every product against rules the person sets themselves.

## Chosen: your own rules, checked everywhere, kept in the browser

- **The rules:** a per-100 g limit for sugars, salt and saturated fat; a minimum Nutri-Score; not ultra-processed (NOVA 4); additives to avoid, picked by name or E number, or with "Add to the additives I avoid" on a guide page. Every rule starts empty, and the page says LabelLens doesn't suggest values.
- **Where they show:** a "Your rules" box on product pages and label reads, a row in the comparison table, and in the basket "n of m meet all your rules" plus each item's misses. With no rules set, product pages and label reads carry one line inviting you to set some; the comparison and basket show nothing.
- **Outcomes in words:** Meets, Misses, Not known. Missing data is never a pass: a label read has no Nutri-Score or NOVA group, so those rules are "Not known" there.
- **A limit is met at exactly the limit,** and values show to one decimal so a near miss is visible (33.3 g, not 33 g).
- **Kept in `localStorage`,** like the basket: no account, nothing sent. Stored rules are cleaned on every read, so a broken or tampered value drops out instead of breaking pages.

**Rejected:**
- **Default or suggested values** (for example the UK "high" thresholds as limits): that would turn the site's facts into advice. The high-in flags already show those thresholds as facts.
- **Accounts or a server copy:** more to secure and nothing gained for a demo; a person who wants their rules on another device can set them again in a minute.
- **Marking search results:** search rows don't carry nutrition values, and fetching every product to mark them would multiply API calls.
- **A score out of 100 for each product:** a single number hides which rule failed, and reads as LabelLens's judgement.

## Checked

- Rule matching, boundaries, missing data, storage and cleaning: `web/lib/preferences.test.ts`.
- The form, the box with and without rules, the compare row, the guide's avoid button, and the basket line: component tests.
- Screenshots at 375, 1280 and 1600 px with rules set, and the product page without rules.
