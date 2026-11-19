# 0011: The home page, turned up

Status: accepted. Date: 2026-11-18.

The site read as white and blank: correct, quiet, and forgettable in a demo. Looking through the food and AI sites on minimal.gallery, the memorable ones had type that fills the screen, one strong colour on a warm ground, full-width bands, and (for the AI ones) the working product in the hero.

## Chosen: the label, turned up

- **A warm page, white labels.** `page` (#F4EFE6) behind everything, `paper` white for panels, inputs and labels, so a label reads as a sticker on a pack. Depth still comes from rules, never shadows.
- **A poster headline** sized to its container (`cqi`), so "What's in it?" fills the page width at every size.
- **The product in the hero:** a real label (oats, Cheerios, Coca-Cola: A, C and E) printing in, with its real EAN-13 drawn from its digits.
- **Colour that is data:** the only large colour is the shelf strip, the five Nutri-Score colours sized by the real share of each grade. The rule "Nutri-Score colours only for Nutri-Score data" holds.
- **Ink bands** for the ticker of findings, the eval numbers, and the footer, with a lighter focus ring there (8:1 on black).

**Rejected:**
- **Quiet polish,** keeping the white page: lowest risk, but it doesn't fix "blank".
- **A dark page:** striking, but food labels are white stickers. It would have pulled every page away from the label identity.
- **Photography or illustration:** licensing, weight, and nothing to say that the data doesn't say better.

## Checked

- **Contrast,** tested from the tokens: `ink-muted` on `page` is 4.65:1, `paper-muted` on ink 10.6:1, `focus-inverse` on ink 8:1.
- **The ticker** pauses on hover and with a button (WCAG 2.2.2), and stands still under reduced motion.
- **Lighthouse** on a local production build: home 100 in every category, product 92 to 100, dashboard 100.
- **The barcode's bars** equal the pattern the real reader decoded in the scanner test. Scanning the specimen off a screen with a phone has not been tried yet.
