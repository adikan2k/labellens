# 0015: My basket

Status: draft for Aditya to rewrite. Date: 2026-11-18.

People don't shop one product at a time. A basket lets them see a week's shopping together and find a better version of each item, while LabelLens still only states facts.

## Chosen: barcodes in the browser, facts about them together, one swap each

- **Add from anywhere:** any product page (including one reached by a scan), or a label read that matched a product. The header shows the count.
- **Kept in `localStorage`** as a list of barcodes only: no account, nothing sent. Capped at 30 items, and the stored list is cleaned on every read (digits only, no repeats).
- **The summary is counts, never a score:**
  - how many products and how many are ultra-processed;
  - the Nutri-Score mix as a bar, in the grade colours with each letter;
  - high-in counts by the UK criteria (0014);
  - every additive across the basket, flagged ones first.
  
  A missing grade or NOVA group is counted as missing, not left out.
- **One swap per item:** the top swap from the existing swaps endpoint, the same rule the product page uses. Grade A items aren't looked up. "Swap" replaces the item in place, keeping the order, so the summary changes in front of you.
- **Sharing:** `/basket?codes=…` opens a read-only copy with "Save as my basket". The link holds barcodes and nothing else.
- **No API change:** products and swaps come from the endpoints that already existed. The summary is computed in the browser by a pure function (`summarise` in `web/lib/basket.ts`).

**Rejected:**
- **A basket score or grade** ("your basket: C"): it would read as a judgement of the person, and a single number hides what drives it.
- **Accounts or a server copy:** more to secure and run, and nothing gained for a demo.
- **Product names or notes in the share link:** barcodes are enough to rebuild the basket, and a link with less in it is safer to paste anywhere.
- **Swaps in a shared basket:** it's read-only, so offering swaps there would invite changes that go nowhere. They appear once it's saved as yours.
- **No item limit:** each item is a product request and a swap request, so 30 keeps the page fast and the API calls bounded.

## Checked

- The store (barcodes only, no repeats, 30 at most), adding, removing, swapping in place, the share link, and the summary maths: `web/components/basket/basket.test.tsx`.
- The page: empty state, products together with a swap, a shared basket staying read-only until saved, a barcode no longer in the data, and (since 0013) the rules line.
- Screenshots of empty and filled baskets at 375 and 1280 px, and a shared basket at 1280 px: `docs/design/basket/`.
