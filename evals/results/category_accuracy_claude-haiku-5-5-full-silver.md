# Category accuracy: claude-haiku-5-5-full-silver

Measured 2026-11-18T00:59:39+00:00: `claude-haiku-5-5`, prompt `categories-v1`, inputs: name, brand and ingredients. Cost $0.0044 (0 when every answer was cached).

Labels: 200 products labelled by Claude Opus 5.5 (an AI model, not a person).

| | Accuracy |
| --- | ---: |
| **All gold products** | **90.0% (180/200)** |
| dev half | 88.6% (93/105) |
| test half | 91.6% (87/95) |
| Gold products Open Food Facts' tags place | 90.8% (109/120) |
| Gold products they do not (what the fill is for) | 88.8% (71/80) |
| Baseline: Open Food Facts' tags, where they give a category | 87.5% (105/120) |

Target: 90%. This run **meets** it. Invalid answers (counted wrong): 0.

## Most common confusions

| Gold label | Model said | Count |
| --- | --- | ---: |
| Canned goods and soups | Fruits and vegetables | 3 |
| Candy and chocolate | Chips, crackers and salty snacks | 1 |
| Sauces, dressings and condiments | Fruits and vegetables | 1 |
| Pasta, rice and grains | Prepared meals and pizza | 1 |
| Fruits and vegetables | Prepared meals and pizza | 1 |
| Milk, cream and plant milks | Other or unclear | 1 |
| Oils, baking and sweeteners | Sauces, dressings and condiments | 1 |
| Fresh meat and poultry | Deli meats, sausages and bacon | 1 |
| Water, coffee and tea | Juices and fruit drinks | 1 |
| Water, coffee and tea | Sodas and soft drinks | 1 |
| Supplements and protein powders | Sodas and soft drinks | 1 |
| Chips, crackers and salty snacks | Prepared meals and pizza | 1 |
| Candy and chocolate | Other or unclear | 1 |
| Cheese | Prepared meals and pizza | 1 |
| Breakfast cereals and oats | Nuts, seeds and snack bars | 1 |

## By category

| Category | Gold products | Recall | Precision |
| --- | ---: | ---: | ---: |
| Prepared meals and pizza | 17 | 100% | 81% |
| Candy and chocolate | 13 | 85% | 100% |
| Chips, crackers and salty snacks | 13 | 92% | 92% |
| Sauces, dressings and condiments | 13 | 77% | 91% |
| Oils, baking and sweeteners | 12 | 83% | 100% |
| Deli meats, sausages and bacon | 12 | 100% | 92% |
| Cookies, cakes and pastries | 11 | 100% | 100% |
| Canned goods and soups | 9 | 67% | 100% |
| Ice cream and frozen desserts | 9 | 100% | 100% |
| Fruits and vegetables | 9 | 89% | 67% |
| Water, coffee and tea | 9 | 78% | 100% |
| Cheese | 8 | 88% | 88% |
| Nuts, seeds and snack bars | 8 | 100% | 89% |
| Breakfast cereals and oats | 7 | 86% | 100% |
| Juices and fruit drinks | 7 | 100% | 88% |
| Supplements and protein powders | 7 | 86% | 100% |
| Bread and tortillas | 6 | 100% | 86% |
| Milk, cream and plant milks | 6 | 83% | 100% |
| Fish and seafood | 5 | 100% | 100% |
| Pasta, rice and grains | 4 | 75% | 100% |
| Sodas and soft drinks | 4 | 100% | 67% |
| Other or unclear | 3 | 100% | 50% |
| Yogurt and dairy desserts | 3 | 100% | 100% |
| Fresh meat and poultry | 2 | 50% | 100% |
| Spreads, jams and nut butters | 2 | 100% | 100% |
| Eggs, tofu and meat alternatives | 1 | 100% | 100% |
