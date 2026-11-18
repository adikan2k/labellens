# Category accuracy: claude-haiku-5-5-name-only-silver

Measured 2026-11-18T08:12:07+00:00: `claude-haiku-5-5`, prompt `categories-v1`, inputs: name and brand only. Cost $0.0000 (0 when every answer was cached).

Labels: 200 products labelled by Claude Opus 5.5 (an AI model, not a person).

| | Accuracy |
| --- | ---: |
| **All labelled products** | **175/200: 87.5% (82.2–91.4%)** |
| dev half | 90/105: 85.7% (77.8–91.1%) |
| test half | 85/95: 89.5% (81.7–94.2%) |
| Products Open Food Facts' tags place | 104/120: 86.7% (79.4–91.6%) |
| Products they do not (what the fill is for) | 71/80: 88.8% (80.0–94.0%) |
| Baseline: Open Food Facts' tags, where they give a category | 105/120: 87.5% (80.4–92.3%) |

Ranges in brackets are 95% confidence intervals (Wilson score): with this few cases the true rate could plausibly be anywhere in the range, so a gap smaller than the ranges may be noise.

Target: 90%. This run **misses** it. Invalid answers (counted wrong): 0.

## Most common confusions

| Label | Model said | Count |
| --- | --- | ---: |
| Canned goods and soups | Fruits and vegetables | 2 |
| Candy and chocolate | Cookies, cakes and pastries | 2 |
| Candy and chocolate | Yogurt and dairy desserts | 1 |
| Pasta, rice and grains | Prepared meals and pizza | 1 |
| Ice cream and frozen desserts | Prepared meals and pizza | 1 |
| Spreads, jams and nut butters | Cookies, cakes and pastries | 1 |
| Juices and fruit drinks | Supplements and protein powders | 1 |
| Milk, cream and plant milks | Other or unclear | 1 |
| Nuts, seeds and snack bars | Other or unclear | 1 |
| Water, coffee and tea | Juices and fruit drinks | 1 |
| Supplements and protein powders | Sodas and soft drinks | 1 |
| Prepared meals and pizza | Pasta, rice and grains | 1 |
| Deli meats, sausages and bacon | Fresh meat and poultry | 1 |
| Juices and fruit drinks | Fruits and vegetables | 1 |
| Cheese | Prepared meals and pizza | 1 |

## By category

| Category | Labelled products | Recall | Precision |
| --- | ---: | ---: | ---: |
| Prepared meals and pizza | 17 | 82% | 82% |
| Candy and chocolate | 13 | 69% | 100% |
| Chips, crackers and salty snacks | 13 | 100% | 100% |
| Sauces, dressings and condiments | 13 | 92% | 92% |
| Oils, baking and sweeteners | 12 | 83% | 91% |
| Deli meats, sausages and bacon | 12 | 92% | 100% |
| Cookies, cakes and pastries | 11 | 100% | 79% |
| Canned goods and soups | 9 | 67% | 100% |
| Ice cream and frozen desserts | 9 | 89% | 100% |
| Fruits and vegetables | 9 | 100% | 75% |
| Water, coffee and tea | 9 | 89% | 100% |
| Cheese | 8 | 88% | 100% |
| Nuts, seeds and snack bars | 8 | 88% | 78% |
| Breakfast cereals and oats | 7 | 86% | 100% |
| Juices and fruit drinks | 7 | 71% | 83% |
| Supplements and protein powders | 7 | 86% | 86% |
| Bread and tortillas | 6 | 100% | 86% |
| Milk, cream and plant milks | 6 | 83% | 100% |
| Fish and seafood | 5 | 100% | 100% |
| Pasta, rice and grains | 4 | 75% | 60% |
| Sodas and soft drinks | 4 | 100% | 80% |
| Other or unclear | 3 | 100% | 50% |
| Yogurt and dairy desserts | 3 | 100% | 75% |
| Fresh meat and poultry | 2 | 100% | 50% |
| Spreads, jams and nut butters | 2 | 50% | 100% |
| Eggs, tofu and meat alternatives | 1 | 100% | 100% |
