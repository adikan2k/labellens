"""Reading a food label from a photo: Claude reads it, LabelLens explains it from its data.

- `images`: what an upload may be (type by magic bytes, size, count).
- `reading`: the one model call, with structured output (`LabelReading`).
- `normalise`: per serving to per 100 g, units, and the pipeline's bounds, in code.
- `service`: limits, the run log, matching to our products, explainers and suggestions.
"""
