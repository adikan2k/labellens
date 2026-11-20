# 0016: The graph in three columns

Status: accepted. Date: 2026-11-20.

An AI review of the live site called the graph page the weakest on the site: "a tangle of unlabelled dots with no legend". The first fix gave each kind of node a shape and added a key. That made the tangle easier to read, but the layout itself was the problem.

## Chosen: draw the three layers the data already has

Every neighbourhood the API returns has the same shape: one product, the things it is linked to (brand, categories, additives, ingredients), and the other products linked to those same things. The page now draws exactly that, left to right.

- **Position means something.** Left is the product, the middle is what it is linked to, the right is what shares it. The force-directed layout put nodes wherever the forces settled.
- **Every node has a readable name.** In the old drawing of Cheerios, 57 of 79 nodes were other products and most had no label until hovered.
- **It answers a question.** The right column ranks products by how much they share with the centre, with the count. Selecting one lists what is shared; selecting an ingredient or additive lists every product that has it.
- **Plain page elements, not WebGL.** Rows are buttons in lists and the lines are SVG. It works by keyboard and screen reader without a second view, and three libraries (Sigma, graphology and its layout) are gone from the page.
- **Fixed row height.** Every row is one line, 2rem tall, so the lines between columns are computed from row numbers and nothing is measured in the browser.
- **One product, one row.** Other listings of the same name are folded together, and listings of the centre's own name are left out, the same rule search uses (#39).

**Rejected:**
- **Keeping the force-directed drawing with shapes and a key** (the first fix): legible marks, but position still carried no meaning and most nodes stayed unnamed.
- **A radial layout** (hubs on an inner ring, products on an outer one): it keeps the look of a network, but 57 names around a circle still cannot all be shown.
- **Both views behind a switch:** two drawings to keep correct, for a page with one job.
- **Colour by kind:** colour on this site only ever means a Nutri-Score grade (DESIGN.md).
- **Showing all 57 products on the right:** a column over 1,800 px tall whose lower half shares one ingredient such as salt. The 16 that share the most are shown; all of them are in the list below.

**What is lost:** the page no longer looks like a network at a glance. It is still nodes and links, read from the same graph database.

## Checked

- The column model (grouping, ranking, folding, the limit, narrowing to a hub): `web/components/graph/graph.test.tsx`.
- The page: the three columns, selecting a hub and a product, the panel's list of what is shared, the list view, re-centring.
- Screenshots at 375, 1280 and 1600 px, with a product selected and with an ingredient selected: `docs/design/graph-columns/`.
