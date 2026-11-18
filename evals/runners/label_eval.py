"""How well LabelLens reads real labels: Open Food Facts photos against Open Food Facts data.

    uv run python -m evals.runners.label_eval --limit 30            # prints the estimate
    uv run python -m evals.runners.label_eval --limit 30 --yes      # sends (about $0.01 on Haiku)
    uv run python -m evals.runners.label_eval --limit 30 --model eval --yes   # Sonnet

Each label is read by the same code as POST /label (api/app/label/reading.py, then
normalise.py), from its ingredients photo and its nutrition photo. Reads are cached in
evals/cache/label_runs.jsonl by prompt version, model and photo hashes, so reruns cost $0.

Scored:
- Nutrients: each of the seven per 100 g values Open Food Facts has, right when within 10%
  (or 0.5 g; 0.1 g for salt; 10 kcal for energy, whichever is larger). A value not read
  counts as wrong.
- Labels: the share with every known nutrient right.
- Additives: the additives LabelLens matched from the read (as POST /label matches them,
  against the serving tables), compared with Open Food Facts' by E-number family, so E322
  and E322i are one. Precision and recall over all labels.
Open Food Facts' data is entered by contributors, so a miss can be the truth's fault; the
report lists every miss for a person to check.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evals.datasets.build_labels import image_path
from evals.datasets.build_labels import load as load_dataset
from evals.runners.stats import INTERVAL_NOTE, ci95, pct_ci

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "evals" / "cache" / "label_runs.jsonl"
RESULTS = ROOT / "evals" / "results"
LOCAL_DB = "postgresql://labellens:labellens@localhost:54329/labellens"

# Upper bounds for the printed estimate: Claude scales a photo to at most ~1,600 tokens.
EST_INPUT_TOKENS = 2 * 1600 + 1100
EST_OUTPUT_TOKENS = 500

NUTRIENTS = {
    "energy_kcal_100g": ("Energy", 10.0),
    "fat_100g": ("Fat", 0.5),
    "saturated_fat_100g": ("Saturated fat", 0.5),
    "salt_100g": ("Salt", 0.1),
    "fiber_100g": ("Fiber", 0.5),
    "sugars_100g": ("Sugars", 0.5),
    "proteins_100g": ("Protein", 0.5),
}
RELATIVE = 0.10
FAMILY = re.compile(r"^en:e(\d+)")


def run_key(model: str, prompt_version: str, photos: list[bytes]) -> str:
    digests = "|".join(hashlib.sha256(p).hexdigest() for p in photos)
    return hashlib.sha256(f"{prompt_version}|{model}|{digests}".encode()).hexdigest()[:24]


class RunCache:
    def __init__(self, path: Path = CACHE):
        self.path = path
        self.rows: dict[str, dict[str, Any]] = {}
        if path.exists():
            for line in path.read_text("utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row

    def add(self, row: dict[str, Any]) -> None:
        self.rows[row["key"]] = row
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self.rows.values(), key=lambda r: (r["model"], r["id"], r["key"]))
        with open(self.path, "w", encoding="utf-8", newline="\n") as f:
            for r in ordered:
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def photos_of(item: dict[str, Any]) -> list[bytes]:
    paths = [image_path(item, image["kind"]) for image in item["images"]]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise SystemExit(
            f"Missing {missing[0].name}: run `uv run python -m evals.datasets.build_labels "
            "--download` first."
        )
    return [p.read_bytes() for p in paths]


def estimate_usd(n: int, prices: tuple[float, float]) -> float:
    return n * (EST_INPUT_TOKENS * prices[0] + EST_OUTPUT_TOKENS * prices[1]) / 1e6


def read_all(
    items: list[dict[str, Any]],
    *,
    client_factory: Callable[[], Any],
    model: str,
    cache: RunCache,
    prices: tuple[float, float],
    yes: bool,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]] | None:
    """Each label's cached read, sending the missing ones only with --yes."""
    from api.app.label import images as label_images
    from api.app.label.reading import PROMPT_VERSION, ReadFailed, read

    keyed = [(item, run_key(model, PROMPT_VERSION, photos_of(item))) for item in items]
    todo = [(item, key) for item, key in keyed if key not in cache.rows]
    log(
        f"{len(items) - len(todo)} cached, {len(todo)} to read with {model} "
        f"({PROMPT_VERSION}; at most ${estimate_usd(len(todo), prices):.4f})."
    )
    if todo and not yes:
        log("Nothing sent. Add --yes to run it.")
        return None
    if todo:
        client = client_factory()
        for item, key in todo:
            started = time.perf_counter()
            photos = label_images.check(photos_of(item))
            try:
                result = read(client, model, photos)
                reading, usage, stop = result.reading.model_dump(), result.usage, result.stop_reason
            except ReadFailed as failure:
                reading, usage, stop = None, failure.usage, str(failure)
            cache.add(
                {
                    "key": key,
                    "id": item["id"],
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "reading": reading,
                    "stop_reason": stop,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                    "cost_usd": round(usage.cost(model), 6),
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                }
            )
            log(f"  {item['id']} read in {time.perf_counter() - started:.1f} s")
    return [cache.rows[key] for _, key in keyed]


def nutrient_right(key: str, read: float | None, truth: float) -> bool:
    if read is None:
        return False
    return abs(read - truth) <= max(RELATIVE * abs(truth), NUTRIENTS[key][1])


def family(additive_id: str) -> str | None:
    match = FAMILY.match(additive_id)
    return match.group(1) if match else None


AUDIT_PATH = ROOT / "evals" / "datasets" / "labels_audit.json"


def load_audit(path: Path = AUDIT_PATH) -> dict[str, dict[str, Any]]:
    data = json.loads(path.read_text("utf-8")) if path.exists() else {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def truth_of(item: dict[str, Any], audit: dict[str, Any] | None) -> tuple[dict, list[str], str]:
    """(nutrition, additives, why excluded) for one label: Open Food Facts as it is, or with
    the corrections checked against its photo."""
    nutrition = dict(item["truth"]["nutrition"])
    additives = list(item["truth"]["additives"])
    entry = (audit or {}).get(item["id"], {})
    nutrition.update(entry.get("nutrition", {}))
    if "additives" in entry:
        additives = entry["additives"]
    return nutrition, additives, entry.get("exclude", "")


def score(
    items: list[dict[str, Any]],
    runs: list[dict[str, Any]],
    matched: list[set[str]],
    audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Counts for the report. `matched` holds each label's matched additive families.

    Without `audit`, the truth is Open Food Facts as it is. With it, the corrections apply,
    excluded labels are left out, and a nutrient the label does not print (Open Food Facts
    stores 0, the read finds nothing) is not scored: reading nothing there is right."""
    from api.app.label.normalise import nutrition_per_100g
    from api.app.label.reading import LabelReading

    audited = audit is not None
    per_nutrient = {k: [0, 0] for k in NUTRIENTS}
    by_language: dict[str, dict[str, int]] = {}
    labels_right = labels = food = not_printed = 0
    tp = predicted = actual = 0
    scored, excluded = [], []
    for item, run, mine in zip(items, runs, matched, strict=True):
        truth, truth_additives, why = truth_of(item, audit)
        if why:
            excluded.append({"id": item["id"], "why": why})
            continue
        reading = LabelReading(**run["reading"]) if run["reading"] else None
        values: dict[str, Any] = nutrition_per_100g(reading)[0] if reading else {}
        food += bool(reading and reading.is_food_label)
        misses = []
        known = right = 0
        for key in NUTRIENTS:
            if truth.get(key) is None:
                continue
            if audited and truth[key] == 0 and values.get(key) is None:
                not_printed += 1
                continue
            known += 1
            ok = nutrient_right(key, values.get(key), truth[key])
            right += ok
            per_nutrient[key][0] += ok
            per_nutrient[key][1] += 1
            if not ok:
                misses.append(f"{NUTRIENTS[key][0]}: read {values.get(key)}, truth {truth[key]}")
        all_right = known > 0 and right == known
        labels += 1
        labels_right += all_right
        lang = by_language.setdefault(item["language"], {"labels": 0, "right": 0, "n": 0, "k": 0})
        lang["labels"] += 1
        lang["right"] += all_right
        lang["n"] += known
        lang["k"] += right

        theirs = {f for f in (family(a) for a in truth_additives) if f}
        tp += len(mine & theirs)
        predicted += len(mine)
        actual += len(theirs)
        extra, missed = sorted(mine - theirs), sorted(theirs - mine)
        if extra:
            misses.append("additives not in the truth: " + ", ".join(f"E{f}" for f in extra))
        if missed:
            misses.append("additives missed: " + ", ".join(f"E{f}" for f in missed))
        scored.append({"id": item["id"], "all_right": all_right, "misses": misses})

    nutrient_k = sum(v[0] for v in per_nutrient.values())
    nutrient_n = sum(v[1] for v in per_nutrient.values())
    return {
        "audited": audited,
        "labels": labels,
        "excluded": excluded,
        "not_printed": not_printed,
        "read_as_food": food,
        "labels_all_right": labels_right,
        "nutrients_right": nutrient_k,
        "nutrients_known": nutrient_n,
        "per_nutrient": per_nutrient,
        "by_language": by_language,
        "additives": {"true_positive": tp, "predicted": predicted, "actual": actual},
        "scored": scored,
    }


def matched_families(runs: list[dict[str, Any]], database_url: str) -> list[set[str]]:
    """The additive families POST /label would match for each read, from the serving tables."""
    from psycopg.rows import dict_row

    from api.app.db import DictConnection
    from api.app.label.reading import LabelReading
    from api.app.label.service import explain

    out = []
    with closing(
        DictConnection.connect(database_url, row_factory=dict_row, autocommit=True)
    ) as conn:
        for run in runs:
            if not run["reading"]:
                out.append(set())
                continue
            additives = explain(conn, LabelReading(**run["reading"]))["additives"]
            out.append({f for f in (family(a["additive_id"]) for a in additives) if f})
    return out


def _measures(s: dict[str, Any]) -> list[tuple[str, str]]:
    a = s["additives"]
    return [
        (
            "Nutrient values right (within 10%)",
            f"{pct_ci(s['nutrients_right'], s['nutrients_known'])} of {s['nutrients_known']}",
        ),
        (
            "Labels with every nutrient right",
            f"{pct_ci(s['labels_all_right'], s['labels'])} of {s['labels']}",
        ),
        (
            "Additives found that are on the label (precision)",
            f"{pct_ci(a['true_positive'], a['predicted'])} of {a['predicted']}",
        ),
        (
            "Additives on the label that were found (recall)",
            f"{pct_ci(a['true_positive'], a['actual'])} of {a['actual']}",
        ),
    ]


def to_markdown(
    raw: dict[str, Any],
    audited: dict[str, Any],
    items: list[dict[str, Any]],
    audit: dict[str, Any],
    meta: dict[str, Any],
) -> str:
    lines = [
        f"# Label reading: {meta['model']}",
        "",
        f"{meta['measured_at']} · model `{meta['model']}` · prompt `{meta['prompt_version']}` · "
        f"{len(items)} labels · ${meta['cost_usd']:.4f} · p50 {meta['p50_s']:.1f} s per label",
        "",
        "Open Food Facts photos (ingredients and nutrition panel) of the most-scanned products in "
        "the US data, two at most per category, 22 with English labels and 8 in other "
        "languages, read by the same code as `POST /label`. Dataset: "
        "`evals/datasets/labels.jsonl` (`evals/datasets/build_labels.py`). Photos: Open Food "
        "Facts contributors, CC BY-SA.",
        "",
        "Two truths. **Open Food Facts as is** scores against its own data, which contributors "
        "enter. **Checked against the photos** applies `evals/datasets/labels_audit.json`: "
        "values corrected where the photo shows Open Food Facts is wrong, labels left out "
        "whose photo is of something else or unreadable, and nutrients the label does not "
        f"print not scored ({audited['not_printed']} such values, stored by Open Food Facts as "
        "0). The corrections were made by reading each photo; they are listed below to check.",
        "",
        "Read the additive figures with one caution: the prompt (v1 to v3) and the list of US "
        "label names in `api/app/additives.py` (cellulose gum, soy lecithin and so on) were "
        "improved after earlier runs on these same 30 labels showed what was missed, so they "
        "are tuned to this set. The nutrient figures barely moved between prompt versions.",
        "",
        "| Measure | Open Food Facts as is | Checked against the photos |",
        "| --- | --- | --- |",
    ]
    for (name, as_is), (_, checked) in zip(_measures(raw), _measures(audited), strict=True):
        lines.append(f"| {name} | {as_is} | {checked} |")
    lines.append(
        f"| Photos read as a food label | {pct_ci(raw['read_as_food'], raw['labels'])} | "
        f"{pct_ci(audited['read_as_food'], audited['labels'])} |"
    )
    lines += [
        "",
        "## Checked against the photos, by nutrient",
        "",
        "| Nutrient | Right |",
        "| --- | --- |",
    ]
    for key, (k, n) in audited["per_nutrient"].items():
        lines.append(f"| {NUTRIENTS[key][0]} | {pct_ci(k, n)} of {n} |")
    lines += [
        "",
        "## Checked against the photos, by label language",
        "",
        "| Labels | Nutrients right | All right |",
        "| --- | --- | --- |",
    ]
    for lang, v in sorted(audited["by_language"].items()):
        name = "English" if lang == "en" else "Other languages"
        nutrients, labels = pct_ci(v["k"], v["n"]), pct_ci(v["right"], v["labels"])
        lines.append(f"| {name} ({v['labels']}) | {nutrients} | {labels} |")
    lines += ["", INTERVAL_NOTE, "", "## The corrections", ""]
    by_id = {i["id"]: i for i in items}
    for item_id, entry in sorted(audit.items()):
        item = by_id.get(item_id)
        if item is None:
            continue
        what = entry.get("exclude") or entry.get("note", "")
        verb = "left out" if entry.get("exclude") else "corrected"
        lines.append(f"- **{item_id}** {item['name']} (`{item['code']}`), {verb}: {what}")
    lines += ["", "## Misses, checked against the photos", ""]
    any_miss = False
    for row in audited["scored"]:
        if row["misses"]:
            any_miss = True
            item = by_id[row["id"]]
            head = f"- **{row['id']}** {item['name']} ({item['brand']}, `{item['code']}`): "
            lines.append(head + "; ".join(row["misses"]))
    if not any_miss:
        lines.append("None.")
    return "\n".join(lines) + "\n"


def _intervals(s: dict[str, Any]) -> dict[str, list[float]]:
    a = s["additives"]
    return {
        "nutrients": ci95(s["nutrients_right"], s["nutrients_known"]),
        "labels_all_right": ci95(s["labels_all_right"], s["labels"]),
        "additive_precision": ci95(a["true_positive"], a["predicted"]),
        "additive_recall": ci95(a["true_positive"], a["actual"]),
    }


def main(argv: list[str] | None = None) -> int:
    from api.app.config import get_settings, price_per_mtok
    from api.app.label.reading import PROMPT_VERSION
    from pipeline.enrich.categories import client_factory

    parser = argparse.ArgumentParser(description="Label reading on Open Food Facts photos.")
    parser.add_argument("--limit", type=int, required=True, help="most labels to read")
    parser.add_argument("--yes", action="store_true", help="send (costs money); else estimate")
    parser.add_argument("--model", choices=["default", "eval"], default="default")
    parser.add_argument("--database-url", default=LOCAL_DB, help="a database with `serving`")
    args = parser.parse_args(argv)

    settings = get_settings()
    model = settings.model_default if args.model == "default" else settings.model_eval
    prices = price_per_mtok(model)
    items = load_dataset()[: max(args.limit, 0)]
    runs = read_all(
        items,
        client_factory=client_factory,
        model=model,
        cache=RunCache(),
        prices=prices,
        yes=args.yes,
    )
    if runs is None:
        return 0

    matched = matched_families(runs, args.database_url)
    audit = load_audit()
    raw, audited = score(items, runs, matched), score(items, runs, matched, audit)
    durations = sorted(r["duration_ms"] for r in runs)
    meta = {
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "cost_usd": round(sum(r["cost_usd"] for r in runs), 6),
        "p50_s": durations[len(durations) // 2] / 1000 if durations else 0.0,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    stem = f"label_reading_{model}"
    report = to_markdown(raw, audited, items, audit, meta)
    (RESULTS / f"{stem}.md").write_text(report, "utf-8", newline="\n")
    payload = {
        **meta,
        "as_is": {k: v for k, v in raw.items() if k != "scored"} | {"intervals": _intervals(raw)},
        "checked": {k: v for k, v in audited.items() if k != "scored"}
        | {"intervals": _intervals(audited)},
    }
    text = json.dumps(payload, indent=2) + "\n"
    (RESULTS / f"{stem}.json").write_text(text, "utf-8", newline="\n")
    for name, s in (("As is", raw), ("Checked", audited)):
        a = s["additives"]
        print(
            f"{name}: nutrients {pct_ci(s['nutrients_right'], s['nutrients_known'])}, labels "
            f"{pct_ci(s['labels_all_right'], s['labels'])}, additive precision "
            f"{pct_ci(a['true_positive'], a['predicted'])}, recall "
            f"{pct_ci(a['true_positive'], a['actual'])}"
        )
    print(f"Wrote evals/results/{stem}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
