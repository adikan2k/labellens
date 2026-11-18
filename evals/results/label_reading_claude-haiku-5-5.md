# Label reading: claude-haiku-5-5

2026-11-18T23:37:48+00:00 · model `claude-haiku-5-5` · prompt `label-v3` · 30 labels · $0.0195 · p50 1.4 s per label

Open Food Facts photos (ingredients and nutrition panel) of the most-scanned products in the US data, two at most per category, 22 with English labels and 8 in other languages, read by the same code as `POST /label`. Dataset: `evals/datasets/labels.jsonl` (`evals/datasets/build_labels.py`). Photos: Open Food Facts contributors, CC BY-SA.

Two truths. **Open Food Facts as is** scores against its own data, which contributors enter. **Checked against the photos** applies `evals/datasets/labels_audit.json`: values corrected where the photo shows Open Food Facts is wrong, labels left out whose photo is of something else or unreadable, and nutrients the label does not print not scored (26 such values, stored by Open Food Facts as 0). The corrections were made by reading each photo; they are listed below to check.

Read the additive figures with one caution: the prompt (v1 to v3) and the list of US label names in `api/app/additives.py` (cellulose gum, soy lecithin and so on) were improved after earlier runs on these same 30 labels showed what was missed, so they are tuned to this set. The nutrient figures barely moved between prompt versions.

| Measure | Open Food Facts as is | Checked against the photos |
| --- | --- | --- |
| Nutrient values right (within 10%) | 71% (65–77%) of 204 | 98% (95–99%) of 159 |
| Labels with every nutrient right | 33% (19–51%) of 30 | 85% (68–94%) of 27 |
| Additives found that are on the label (precision) | 63% (48–76%) of 43 | 93% (81–98%) of 42 |
| Additives on the label that were found (recall) | 93% (78–98%) of 29 | 98% (87–100%) of 40 |
| Photos read as a food label | 97% (83–99%) | 100% (88–100%) |

## Checked against the photos, by nutrient

| Nutrient | Right |
| --- | --- |
| Energy | 100% (87–100%) of 25 |
| Fat | 100% (87–100%) of 25 |
| Saturated fat | 100% (86–100%) of 23 |
| Salt | 96% (80–99%) of 24 |
| Fiber | 92% (67–99%) of 13 |
| Sugars | 96% (80–99%) of 24 |
| Protein | 100% (87–100%) of 25 |

## Checked against the photos, by label language

| Labels | Nutrients right | All right |
| --- | --- | --- |
| English (20) | 97% (93–99%) | 80% (58–92%) |
| Other languages (7) | 100% (92–100%) | 100% (65–100%) |

Ranges in brackets are 95% confidence intervals (Wilson score): with this few cases the true rate could plausibly be anywhere in the range, so a gap smaller than the ranges may be noise.

## The corrections

- **label-03** SPICY CHICKEN & 'NDUJA PIZZA (`13356194`), left out: The nutrition photo is of a different product (a Lidl chicken stock) filed under this pizza.
- **label-06** Cappy PULPY (`5449000147417`), corrected: The panel prints 159 kJ / 37 kcal and 9 g sugars per 100 ml. The ingredients list E300, E330, E440, E445, E414, E950, E954 and E160a; Open Food Facts lists none.
- **label-07** Le Beurre Tendre (`3451790988677`), corrected: The panel prints 3060 kJ / 744 kcal per 100 g; 375 is wrong (butter).
- **label-10** jaouda Cremy (`6111242100305`), left out: The nutrition photo shows the front of the cup; the panel is out of focus and unreadable.
- **label-13** Purified Drinking Water (`0078742040370`), corrected: The ingredients list calcium chloride (E509) and sodium bicarbonate (E500).
- **label-15** Coconut Water (`0898999000503`), corrected: 11 g sugars per 240 ml is 4.58 g per 100 ml; the ingredients list ascorbic acid (E300).
- **label-16** Chocolate con leche y almendras (`8425197712024`), corrected: The panel prints 6.9 g protein and 0.11 g salt per 100 g.
- **label-17** High Quality Protein (`0811620022118`), corrected: 230 mg sodium per 340 ml is 0.17 g salt per 100 ml. Ingredients: carrageenan, cellulose gel and gum, acesulfame potassium, sucralose, stevia leaf extract.
- **label-19** SNACK POPPÉ (`3245550078674`), corrected: The panel prints 9.7 g fat, 6.9 g sugars and 1.62 g salt per 100 g.
- **label-20** Ancient Grains Probiotic Granola (`0096619194261`), corrected: 5 g protein per 55 g serving is 9.09 g per 100 g.
- **label-24** Fromage Blanc Nature (`6111246721261`), left out: The 'nutrition' photo is a screenshot of a chatbot's answer, not a label.
- **label-28** Pains au lait (`3256540000698`), corrected: The panel prints 1.1 g salt per 100 g.

## Misses, checked against the photos

- **label-08** Cream cheese (Original, `6111246721278`): Sugars: read 3.1, truth 0.0
- **label-09** White Ciabattin (Jason's Sourdough, `5025125000006`): additives not in the truth: E170
- **label-11** Eau (Aïn lfrane, `6111251420166`): Salt: read None, truth 0.001
- **label-12** Dark chocolate 50% Cocoa (Fin Carré, `20005832`): Fiber: read 8.5, truth 7.5
- **label-17** High Quality Protein (Fairlife, `0811620022118`): additives not in the truth: E307
- **label-23** Prince (LU, `7622210449283`): additives not in the truth: E471
- **label-26** Jben (Jaouda, `6111242106949`): additives missed: E407
