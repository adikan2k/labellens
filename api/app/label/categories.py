"""The categories a label can be placed in: the leaves of pipeline/dbt/seeds/dim_categories.csv.

A constant here, not read from the seed, because the API image ships without the pipeline;
api/tests/test_label.py checks the two agree.
"""

LEAF_CATEGORIES: dict[str, str] = {
    "sodas": "Sodas and soft drinks",
    "juices": "Juices and fruit drinks",
    "water-coffee-tea": "Water, coffee and tea",
    "salty-snacks": "Chips, crackers and salty snacks",
    "cookies-cakes": "Cookies, cakes and pastries",
    "candy-chocolate": "Candy and chocolate",
    "frozen-desserts": "Ice cream and frozen desserts",
    "nuts-bars": "Nuts, seeds and snack bars",
    "milk": "Milk, cream and plant milks",
    "cheese": "Cheese",
    "yogurt": "Yogurt and dairy desserts",
    "meat": "Fresh meat and poultry",
    "deli-meats": "Deli meats, sausages and bacon",
    "seafood": "Fish and seafood",
    "eggs-alternatives": "Eggs, tofu and meat alternatives",
    "bread": "Bread and tortillas",
    "breakfast-cereals": "Breakfast cereals and oats",
    "pasta-rice": "Pasta, rice and grains",
    "sauces-condiments": "Sauces, dressings and condiments",
    "spreads": "Spreads, jams and nut butters",
    "cooking-baking": "Oils, baking and sweeteners",
    "canned-soups": "Canned goods and soups",
    "fruit-veg": "Fruits and vegetables",
    "prepared-meals": "Prepared meals and pizza",
    "supplements": "Supplements and protein powders",
    "other": "Other or unclear",
}
