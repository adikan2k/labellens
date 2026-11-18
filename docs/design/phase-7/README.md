# Phase 7 design pass: screenshots

Full-page captures by headless Chrome at 375, 1280 and 1600 px, with real data from the
production API.

- `after-*`: this branch, a local production build (`next build && next start`).
- `before-*`: https://labellens-beige.vercel.app on 2026-11-18, for the pages a fix changed.

- `after-graph-labels-*`: the graph page after the follow-up fix (words on the page width,
  labels that never overlap), from the local dev server (the "N" badge is its indicator) on
  the local dev graph. Captured through Chrome's DevTools protocol at true viewport widths.

The ask captures ran one live question ("What is carrageenan and why is it in yogurt?").
