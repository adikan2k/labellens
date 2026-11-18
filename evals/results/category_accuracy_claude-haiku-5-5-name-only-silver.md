# Category accuracy: claude-haiku-5-5-name-only-silver

Measured 2026-11-18T01:01:40+00:00: `claude-haiku-5-5`, prompt `categories-v1`, inputs: name and brand only. Cost $0.0031 (0 when every answer was cached).

Labels: 200 products labelled by Claude Opus 5.5 (an AI model, not a person).

| | Accuracy |
| --- | ---: |
| **All labelled products** | **87.5% (175/200)** |
| dev half | 85.7% (90/105) |
| test half | 89.5% (85/95) |
| Products Open Food Facts' tags place | 86.7% (104/120) |
| Products they do not (what the fill is for) | 88.8% (71/80) |
| Baseline: Open Food Facts' tags, where they give a category | 87.5% (105/120) |

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
