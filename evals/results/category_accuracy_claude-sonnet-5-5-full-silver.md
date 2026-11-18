# Category accuracy: claude-sonnet-5-5-full-silver

Measured 2026-11-18T08:12:09+00:00: `claude-sonnet-5-5`, prompt `categories-v1`, inputs: name, brand and ingredients. Cost $0.0000 (0 when every answer was cached).

Labels: 200 products labelled by Claude Opus 5.5 (an AI model, not a person).

| | Accuracy |
| --- | ---: |
| **All labelled products** | **184/200: 92.0% (87.4–95.0%)** |
| dev half | 97/105: 92.4% (85.7–96.1%) |
| test half | 87/95: 91.6% (84.3–95.7%) |
| Products Open Food Facts' tags place | 110/120: 91.7% (85.3–95.4%) |
| Products they do not (what the fill is for) | 74/80: 92.5% (84.6–96.5%) |
| Baseline: Open Food Facts' tags, where they give a category | 105/120: 87.5% (80.4–92.3%) |

Ranges in brackets are 95% confidence intervals (Wilson score): with this few cases the true rate could plausibly be anywhere in the range, so a gap smaller than the ranges may be noise.

Target: 90%. This run **meets** it. Invalid answers (counted wrong): 0.

## Most common confusions

| Label | Model said | Count |
| --- | --- | ---: |
| Cookies, cakes and pastries | Other or unclear | 1 |
| Candy and chocolate | Chips, crackers and salty snacks | 1 |
| Pasta, rice and grains | Prepared meals and pizza | 1 |
| Prepared meals and pizza | Fruits and vegetables | 1 |
| Spreads, jams and nut butters | Nuts, seeds and snack bars | 1 |
| Supplements and protein powders | Sodas and soft drinks | 1 |
| Chips, crackers and salty snacks | Other or unclear | 1 |
| Candy and chocolate | Spreads, jams and nut butters | 1 |
| Sodas and soft drinks | Juices and fruit drinks | 1 |
| Prepared meals and pizza | Fresh meat and poultry | 1 |
| Canned goods and soups | Fruits and vegetables | 1 |
| Fish and seafood | Prepared meals and pizza | 1 |
| Bread and tortillas | Chips, crackers and salty snacks | 1 |
| Sauces, dressings and condiments | Cheese | 1 |
| Sauces, dressings and condiments | Oils, baking and sweeteners | 1 |

## By category

| Category | Labelled products | Recall | Precision |
| --- | ---: | ---: | ---: |
| Prepared meals and pizza | 17 | 88% | 88% |
| Candy and chocolate | 13 | 85% | 100% |
| Chips, crackers and salty snacks | 13 | 92% | 86% |
| Sauces, dressings and condiments | 13 | 85% | 100% |
| Oils, baking and sweeteners | 12 | 92% | 92% |
| Deli meats, sausages and bacon | 12 | 100% | 100% |
| Cookies, cakes and pastries | 11 | 91% | 100% |
| Canned goods and soups | 9 | 89% | 100% |
| Ice cream and frozen desserts | 9 | 100% | 100% |
| Fruits and vegetables | 9 | 100% | 82% |
| Water, coffee and tea | 9 | 100% | 100% |
| Cheese | 8 | 100% | 89% |
| Nuts, seeds and snack bars | 8 | 100% | 89% |
| Breakfast cereals and oats | 7 | 100% | 100% |
| Juices and fruit drinks | 7 | 100% | 88% |
| Supplements and protein powders | 7 | 86% | 100% |
| Bread and tortillas | 6 | 83% | 83% |
| Milk, cream and plant milks | 6 | 100% | 100% |
| Fish and seafood | 5 | 80% | 100% |
| Pasta, rice and grains | 4 | 75% | 100% |
| Sodas and soft drinks | 4 | 75% | 75% |
| Other or unclear | 3 | 100% | 60% |
| Yogurt and dairy desserts | 3 | 100% | 100% |
| Fresh meat and poultry | 2 | 100% | 67% |
| Spreads, jams and nut butters | 2 | 50% | 50% |
| Eggs, tofu and meat alternatives | 1 | 100% | 100% |
