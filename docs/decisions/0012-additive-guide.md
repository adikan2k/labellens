# 0012: The additive guide

Status: accepted. Date: 2026-11-18.

Additives were explained only where they appeared: one row on one product page. Nobody could ask the other way round: what is E471, how common is it, and what kind of food is it in? Awareness was the point of this feature, and that needs a page per additive.

## Chosen: a page per additive, computed in the pipeline

- **`/additives`:** all 515 additives that named US products list, most common first (citric acid on 100,764). Filter by name or E number as you type ("E 330", "e-330" and "330" all match), and a "flagged only" box.
- **`/additives/[slug]`:** what it is (the explainer), its function, whether Open Food Facts flags it, how many products list it and what share that is, the five categories that use it most as ink bars, and six example products, best-ranked first.
- **Every additive row links to its guide:** product pages, label reads and the basket.
- **The numbers come from dbt** (`agg_additive_usage`), with tests that the list is consistent and every additive exists in `dim_additives`. The loader stores them on `serving.additives`, so a page is three small reads by key: 4 ms warm on the local database.
- **Slugs are the Open Food Facts id without "en:"** (`/additives/e330`), so the address is the E number people know. Other ids are used whole.
- **Facts only.** The guide says what an additive is and where it turns up, and that Open Food Facts flags it; it never says safe, unsafe or avoid. The flag note says it's their rating of overexposure risk, not a ban.

**Rejected:**
- **Counting at request time** from `serving.products`: a scan of 985,000 rows per page on Neon. The first version counted the total this way (24 ms locally); reading `named_product_count` from the stored stats brought it to 4 ms.
- **Ranking additives as good or bad:** an editorial judgement the data doesn't support, and the line this project keeps is facts, not advice.
- **A page only for flagged additives:** smaller, but most people's question is about the common ones (lecithin, xanthan gum, guar gum).

## Checked

- dbt build on the snapshot: all models and tests pass; 520 additives, 515 used by a named product.
- The loader's dry run: 499.1 MB of Neon's 800 MB.
- API tests on the fixture: list order, slug round trip, counts against the products table, examples and categories, 404.
- Web tests: filter, finder, bars, links from additive rows. Screenshots at 375, 1280 and 1600 px.
- The smoke test checks `/additives`, a guide page, and both web pages.
