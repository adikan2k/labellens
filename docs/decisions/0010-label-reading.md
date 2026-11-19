# 0010: Reading a label from a photo

Status: accepted. Date: 2026-11-18.

LabelLens could only explain products already in Open Food Facts. A photo of the pack removes that limit: `POST /label` and the `/label` page read any label, then explain it from the data.

## The model copies; the code computes

**Chosen:** one Claude Haiku call with structured output (`messages.parse` into `LabelReading`). The model returns what is printed: the values in one column, the serving size, sodium in mg or salt in g, the ingredients in order. Everything derived is plain code in `api/app/label/normalise.py`: per serving to per 100 g, kJ to kcal, sodium to salt, and the pipeline's "can't be true" bounds.
**Why:**
- Arithmetic in code is tested once and never varies; arithmetic in a model varies run to run.
- The page can say what was done ("Converted from per serving (30 g or ml)"), because the code knows.
- A value the label doesn't print stays null and reads "Not listed". Nothing is estimated.
**Rejected:** asking the model for per 100 g values directly (unverifiable, and it guesses when the serving size is unclear), and OCR followed by parsing rules (label layouts vary too much, and it needs a new dependency).

## Additives are matched in the data, not trusted from the model

**Chosen:** the model lists additives as E-numbers where it knows them. The API then looks each up with the existing `get_additive`, and also checks every ingredient by exact name, by its bracketed parts, and against a list of US label names (cellulose gum, soy lecithin, stevia leaf extract).
**Why:** the model's list varied between runs of the same photo: once it listed ascorbic acid, once it didn't. The ingredient list was stable, so the deterministic check makes the result stable.
**Rejected:** the fuzzy word match for ingredients. It would turn "salt" into an additive with salt in its name.

## A match is a suggestion

**Chosen:** a barcode read from the photo wins. Otherwise brand and name go through search, and a hit is accepted only when at least 60% of the label's name words are in the product's name and the brands share a word. The page says "Looks like", never "This is". With no match it offers well-graded products in the category and says they are not swaps.
**Why:** a wrong confident match would show someone the wrong product's grade.

## Names are only what is printed (prompt v3)

Prompt v2 named an unbranded orange drink "Mirinda Orange". The pack was a Coca-Cola product; the brand was nowhere in the photo. v3 says to use null when no name or brand is printed, and the page then shows "This product".

## Limits, cost and privacy

- `app.ask_runs` gained `kind`. Label reads get their own 10 an hour per client and share the $0.50 daily cap with questions. Past the cap the API answers 503 and the page points to the samples.
- A read costs about $0.0007 on Haiku and takes about 1.5 s.
- Photos go to Anthropic and nowhere else. LabelLens stores none, and the Langfuse trace gets `[n images]` in their place; a test checks no image bytes reach it. The extracted text is traced.
- Three sample labels are recorded reads, shown at no cost, so the page still demonstrates itself when the cap is spent.

## The eval, and what it found about the truth

30 of the most-scanned products in the US data with both an ingredients photo and a nutrition photo (22 English labels, 8 in other languages), read by the same code as the API.

| Haiku, prompt v3 | Open Food Facts as is | Checked against the photos |
| --- | --- | --- |
| Nutrient values right | 71% (65–77%) | 98% (95–99%) |
| Labels with every value right | 33% (19–51%) | 85% (68–94%) |
| Additives: precision / recall | 63% / 93% | 93% / 98% |

- **The first score was 69%, and most of the misses were not the reader's.** Looking at the photos: one "nutrition photo" was a chatbot screenshot, one pizza's photo was a chicken stock, butter was stored at 375 kcal where the pack says 744, one salt value was 5e-35, and Open Food Facts stores 0 for nutrients a label never prints. `evals/datasets/labels_audit.json` records each correction, and the report prints both columns.
- **The corrections were made by an AI reading the photos** (Claude, in the session that built this). They are listed in the report so a person can check them. Until someone does, the right-hand column is "checked by a second reader", not ground truth.
- **The additive figures are tuned on this set.** The prompt and the alias list were improved after seeing what earlier runs missed on the same 30 labels. The nutrient figure moved by less than a point across prompt versions, so it is the trustworthy one.
- **Sonnet 5.5 scored the same on nutrients** (98%, prompt v2) at 20 times the cost ($0.38 against $0.019 for 30 labels) and 2.7 s against 1.5 s. Haiku stays.

**Rejected:** scoring only against Open Food Facts as is (it measures the dataset's errors as the reader's), and dropping the uncorrected column (it hides how much the audit moved the number).

## A warm-up for demos

`uv run python -m scripts.warm` runs the smoke test with a patient timeout, then `GET /ready`, which builds the lazily loaded ask agent and label reader and reports today's spend and this address's remaining questions and reads. `--hold` pings every 4 minutes, under Neon's 5-minute suspend. It makes no model call.
**Rejected:** a minimum instance on Cloud Run (bills every hour for a site that is demoed a few times).

## Still open

- A person should check the audit's corrections against the photos.
- The eval's photos are Open Food Facts contributors' photos, mostly clear and flat. Real phone photos of curved, glossy packs will be harder; a set of our own photos would measure that.
- Sonnet has not been rerun on prompt v3.
