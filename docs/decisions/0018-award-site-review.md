# 0018: Finishing the look against award-winning sites

Status: draft, for Aditya to review and edit. Date: 2026-11-25.

Before calling LabelLens finished, Aditya asked for it to be checked against award-winning sites (Awwwards, the Webby winners, Web Design Awards, Site of Sites, and Tabnav's list of best website designs). The site already had its own strong system (DESIGN.md: one label, Nutri-Score colours used only for grades, motion only when something prints). The question was what those sites do well that LabelLens did not, without copying their look.

## Chosen: five changes that show the real thing, bigger, and quieter

Every change was its own pull request, each with screenshots at 375, 1280 and 1600 px in `docs/design/`.

- **Pack photos (#46).** Award sites about products show the product. LabelLens showed a name and numbers only. Product pages, search results, swaps, comparisons and the basket now show Open Food Facts' pack photo, linked rather than copied, with the contributors' CC BY-SA credit on the product page.
- **Big page openings (#47).** The winners open each page with type that fills the screen. Every page title went from the Title size to a new Page size (52 px on phones up to 88 px), the same narrow, heavy face as the home headline.
- **Things to try as cards (#48).** The sample labels on Read a label and the example questions on Ask were a line of underlined links. They are now cards: the label's photo, and each question with one line saying what the agent will do with it.
- **An additive guide you can scan (#49).** One column of 515 additives was 27,000 px tall at 1280 px. It now shows the 50 most common, filters by what additives do (colours, preservatives and six more, each with its count), and offers "Show all 515". Any search or filter searches all of them. The page is about 3,750 px tall.
- **Quiet motion on scroll (#50).** The home page's grade strip wipes in once when it scrolls into view, the same print move as the label, and stays still under reduced motion. Nothing else moves on scroll.

The home hero (#45) was fixed in the same round: a line saying what LabelLens is, and the three main ways in under the search box, so the left half is no longer empty beside the label.

**Rejected:**
- **Numbers that count up** in "How it's measured". I proposed it; DESIGN.md already lists "Number counters that tick up" under Never, and the rule stands. The numbers are still.
- **Fade-and-slide on every section**, parallax and scroll hijacking: common on award sites, and all on DESIGN.md's Never list. One element moves, once.
- **Hosting or resizing the pack photos ourselves** (next/image or a CDN): it would copy Open Food Facts' photos, which About says LabelLens never does. Photos are linked from their server at the sizes it already offers.
- **A new colour for the cards or chips:** colour on this site means a Nutri-Score grade. Cards are white panels with the ink rule; the chosen filter chip is paper on ink.

**What it cost:**
- **Speed on the product page.** The pack photo is now the largest thing on the page, so Lighthouse's largest-paint time is the photo's download. On production that took the product page from 98 to 91 on performance, against a target of 90. Connecting early to the photo server made no measurable difference, so it was not kept. Thumbnails now load Open Food Facts' 100 px photo instead of the 400 px one (6 kB instead of about 30 to 60 kB each), which helps search lists but did not move the product page's score.
- **The grade strip needs JavaScript.** Without it the strip stays hidden, as the dashboard's bars already did.

## Fixed after the round

- **The page description reached Lighthouse too late.** Next.js streams a page's title and description into the body for any browser it does not know as a crawler, and Lighthouse's SEO check read the product page as having no description (91). `htmlLimitedBots: /.*/` puts them in the head for everyone. On a local production build against the live API, SEO went from 91 to 100 on all three runs, and the first paint was no slower (about 765 ms, against 908 ms before).
- **The README's screenshots** were from 2026-11-19 and showed none of this round. The eight that changed were retaken from production.

## Checked

- `uv run python scripts/check.py` on every pull request; CI on main after each merge.
- The production smoke test after the merges: 23 of 23.
- Lighthouse on production after the five merges: home 100 in every category; product 91 on performance and SEO; dashboard 96 on performance, 100 on a rerun.
- Lighthouse on production with the description fix live (`evals/results/lighthouse.md`, 2026-11-25): 100 in every category on home and the dashboard; the product page 100 except performance at 90, exactly the target, with its largest paint (the photo) at 3.6 s.
