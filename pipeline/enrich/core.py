"""Paid model calls for enrichment: a per-item cache, a cost guard, the Batch API, validation.

Every task (categories, explainers) runs through `run`:

1. Each item's cache key is a hash of the task, model, prompt version, call settings and the
   exact input the prompt shows. Items already in the task's output file cost nothing.
2. Uncached items are grouped into requests (`task.group_size` per request), capped by
   `limit`. The estimated tokens and cost are printed; nothing is sent without `yes`.
3. Requests go to the Batch API (half price, usually done within the hour) or, for small eval
   runs, straight to the Messages API. Results are matched by `custom_id`, never by order.
4. Each item's output is validated by the task. Items that fail are sent once more in a new
   request; if they fail again they are stored as invalid (value null), so the next run does
   not pay for them again. Requests that error (rate limits, expiry) are not stored, so the
   next run retries them.

The output files are the cache. They are committed to the repo, so the weekly pipeline and
every machine get the results without paying again.

A submitted batch's id is kept in data/enrich/<task>.json until its results are saved, so a
run interrupted while waiting collects that batch instead of submitting (and paying) twice.
"""

from __future__ import annotations

import hashlib
import json
import math
import tempfile
import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "pipeline" / "enrich" / "outputs"
STATE_DIR = ROOT / "data" / "enrich"
BATCH_DISCOUNT = 0.5
# Conservative: English runs about 4 characters per token, so the estimate errs high.
CHARS_PER_TOKEN = 3.0
EFFORT = "low"

Log = Callable[[str], None]


class InvalidOutput(ValueError):
    """The model's output for one item failed validation."""


@dataclass(frozen=True)
class Item:
    ref: str  # what the output describes: a barcode or an additive or ingredient id
    payload: dict[str, Any]  # exactly what the prompt shows for this item; part of the key


class Task(Protocol):
    name: str
    prompt_version: str
    group_size: int
    max_tokens: int
    output_tokens_per_item: int  # for the estimate; measured on real runs

    def system(self) -> str: ...

    def user_message(self, payloads: Sequence[dict[str, Any]]) -> str:
        """The request text for these items, numbered from 1 in order."""
        ...

    def item_schema(self) -> dict[str, Any]:
        """JSON schema properties for one item's answer, besides its number."""
        ...

    def parse_item(self, payload: dict[str, Any], answer: dict[str, Any]) -> str:
        """The stored value for one item, or InvalidOutput."""
        ...


@dataclass(frozen=True)
class CallSettings:
    model: str
    thinking_off: bool  # Haiku 5.5 allows thinking off at low effort; Sonnet 5.5 does not


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0

    def add(self, usage: Any) -> None:
        self.input_tokens += (
            (getattr(usage, "input_tokens", 0) or 0)
            + (getattr(usage, "cache_read_input_tokens", 0) or 0)
            + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
        )
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        self.requests += 1

    def cost(self, prices: tuple[float, float], batch: bool) -> float:
        rate = BATCH_DISCOUNT if batch else 1.0
        return rate * (self.input_tokens * prices[0] + self.output_tokens * prices[1]) / 1e6


@dataclass
class Estimate:
    items: int
    requests: int
    input_tokens: int
    output_tokens: int
    cost: float


@dataclass
class Summary:
    cached: int = 0
    uncached: int = 0
    estimate: Estimate | None = None
    sent: bool = False
    ok: int = 0
    invalid: int = 0
    errored: int = 0
    usage: Usage = field(default_factory=Usage)
    cost: float = 0.0


def cache_key(task: Task, settings: CallSettings, payload: dict[str, Any]) -> str:
    material = {
        "task": task.name,
        "prompt_version": task.prompt_version,
        "model": settings.model,
        "effort": EFFORT,
        "thinking_off": settings.thinking_off,
        "input": payload,
    }
    text = json.dumps(material, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


# ---- the output file (the cache) -------------------------------------------------------------

ROW_FIELDS = ("key", "ref", "value", "status", "model", "prompt_version")


class OutputStore:
    """A task's results: JSONL for text people review, Parquet for large tables."""

    def __init__(self, path: Path):
        self.path = path

    def load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        if self.path.suffix == ".jsonl":
            rows = [json.loads(line) for line in self.path.read_text("utf-8").splitlines() if line]
        else:
            import duckdb

            with duckdb.connect() as con:
                cursor = con.execute("select * from read_parquet(?)", [str(self.path)])
                names = [d[0] for d in cursor.description]
                rows = [dict(zip(names, values, strict=True)) for values in cursor.fetchall()]
        return {row["key"]: row for row in rows}

    def save(self, rows: dict[str, dict[str, Any]]) -> None:
        """Write every row, sorted so reruns give the same file."""
        ordered = sorted(rows.values(), key=lambda r: (r["ref"], r["key"]))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(
            json.dumps({f: row.get(f) for f in ROW_FIELDS}, ensure_ascii=False) + "\n"
            for row in ordered
        )
        if self.path.suffix == ".jsonl":
            self.path.write_text(lines, "utf-8", newline="\n")
            return
        import duckdb

        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "rows.jsonl"
            staged.write_text(lines, "utf-8", newline="\n")
            columns = ", ".join(f"'{f}': 'VARCHAR'" for f in ROW_FIELDS)
            with duckdb.connect() as con:
                con.execute(
                    f"copy (select * from read_json(?, format='newline_delimited', "
                    f"columns={{{columns}}})) to ? (format parquet, compression zstd)",
                    [str(staged), str(self.path)],
                )


# ---- requests and responses ------------------------------------------------------------------


def response_schema(task: Task) -> dict[str, Any]:
    item = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, **task.item_schema()},
        "required": ["id", *task.item_schema().keys()],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"items": {"type": "array", "items": item}},
        "required": ["items"],
        "additionalProperties": False,
    }


def request_params(task: Task, settings: CallSettings, payloads: Sequence[dict]) -> dict:
    params: dict[str, Any] = {
        "model": settings.model,
        "max_tokens": task.max_tokens,
        "system": task.system(),
        "messages": [{"role": "user", "content": task.user_message(payloads)}],
        "output_config": {
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": response_schema(task)},
        },
    }
    if settings.thinking_off:
        params["thinking"] = {"type": "disabled"}
    return params


def parse_response(task: Task, payloads: Sequence[dict], message: Any) -> list[str | None]:
    """One value per payload, in order; None where the output is missing or invalid."""
    values: list[str | None] = [None] * len(payloads)
    if getattr(message, "stop_reason", None) in ("refusal", "max_tokens"):
        return values
    text = next((b.text for b in message.content if getattr(b, "type", None) == "text"), None)
    try:
        answers = json.loads(text or "")["items"]
    except (ValueError, KeyError, TypeError):
        return values
    by_id: dict[int, dict] = {}
    for answer in answers if isinstance(answers, list) else []:
        if isinstance(answer, dict) and isinstance(answer.get("id"), int):
            by_id.setdefault(answer["id"], answer)  # a repeated id keeps its first answer
    for i, payload in enumerate(payloads):
        answer = by_id.get(i + 1)
        if answer is None:
            continue
        try:
            values[i] = task.parse_item(payload, answer)
        except (InvalidOutput, ValueError, KeyError, TypeError):
            values[i] = None
    return values


def estimate(
    task: Task,
    settings: CallSettings,
    groups: Sequence[Sequence[Item]],
    batch: bool,
    prices: tuple[float, float],
) -> Estimate:
    schema_chars = len(json.dumps(response_schema(task)))
    chars = sum(
        len(task.system()) + len(task.user_message([i.payload for i in g])) + schema_chars
        for g in groups
    )
    items = sum(len(g) for g in groups)
    usage = Usage(
        input_tokens=math.ceil(chars / CHARS_PER_TOKEN),
        output_tokens=items * task.output_tokens_per_item,
    )
    return Estimate(
        items, len(groups), usage.input_tokens, usage.output_tokens, usage.cost(prices, batch)
    )


def _chunks(items: Sequence[Item], size: int) -> Iterator[list[Item]]:
    for start in range(0, len(items), size):
        yield list(items[start : start + size])


# ---- sending ---------------------------------------------------------------------------------


@dataclass
class Outcome:
    values: dict[str, str | None] = field(default_factory=dict)  # key -> value (None: invalid)
    errored: set[str] = field(default_factory=set)


def _send_direct(
    client: Any,
    task: Task,
    settings: CallSettings,
    keyed: list[list[tuple[str, Item]]],
    usage: Usage,
    concurrency: int = 4,
) -> Outcome:
    def one(group: list[tuple[str, Item]]) -> tuple[list[tuple[str, Item]], Any]:
        params = request_params(task, settings, [item.payload for _, item in group])
        try:
            return group, client.messages.create(**params)
        except Exception as error:  # any API failure leaves these items unstored
            return group, error

    outcome = Outcome()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        for group, message in pool.map(one, keyed):
            if isinstance(message, Exception):
                outcome.errored.update(key for key, _ in group)
                continue
            usage.add(message.usage)
            values = parse_response(task, [item.payload for _, item in group], message)
            outcome.values.update({key: v for (key, _), v in zip(group, values, strict=True)})
    return outcome


def _state_path(task: Task) -> Path:
    return STATE_DIR / f"{task.name}.json"


def _send_batch(
    client: Any,
    task: Task,
    settings: CallSettings,
    keyed: list[list[tuple[str, Item]]],
    usage: Usage,
    log: Log,
    poll_seconds: float,
    attempt: int,
) -> Outcome:
    requests = []
    mapping: dict[str, list[str]] = {}
    for n, group in enumerate(keyed):
        custom_id = f"{task.name}-a{attempt}-{n:05d}"
        mapping[custom_id] = [key for key, _ in group]
        requests.append(
            {
                "custom_id": custom_id,
                "params": request_params(task, settings, [item.payload for _, item in group]),
            }
        )
    batch = client.messages.batches.create(requests=requests)
    state = {"batch_id": batch.id, "settings": settings.__dict__, "requests": mapping}
    path = _state_path(task)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), "utf-8")
    log(f"Submitted batch {batch.id} ({len(requests):,} requests). Waiting for results...")
    items = {key: item for group in keyed for key, item in group}
    return _collect(client, task, state, items, usage, log, poll_seconds)


def _collect(
    client: Any,
    task: Task,
    state: dict,
    items: dict[str, Item],
    usage: Usage,
    log: Log,
    poll_seconds: float,
) -> Outcome:
    batch_id = state["batch_id"]
    last = ""
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        if batch.processing_status == "ended":
            break
        counts = batch.request_counts
        line = f"  {batch.processing_status}: {counts.succeeded:,} done, {counts.processing:,} left"
        if line != last:
            log(line)
            last = line
        time.sleep(poll_seconds)

    outcome = Outcome()
    for entry in client.messages.batches.results(batch_id):
        keys = state["requests"].get(entry.custom_id, [])
        if entry.result.type != "succeeded" or any(k not in items for k in keys):
            outcome.errored.update(keys)
            continue
        message = entry.result.message
        usage.add(message.usage)
        values = parse_response(task, [items[k].payload for k in keys], message)
        outcome.values.update(dict(zip(keys, values, strict=True)))
    return outcome


# ---- the run ---------------------------------------------------------------------------------


def run(
    task: Task,
    items: Sequence[Item],
    *,
    client_factory: Callable[[], Any],
    settings: CallSettings,
    store: OutputStore,
    prices: tuple[float, float],
    limit: int,
    yes: bool,
    batch: bool = True,
    log: Log = print,
    poll_seconds: float = 30.0,
) -> Summary:
    summary = Summary()
    rows = store.load()

    def record(outcome: Outcome, final: bool) -> list[tuple[str, Item]]:
        """Store valid values (and invalid ones on the final attempt); return items to retry."""
        retry = []
        for key, value in outcome.values.items():
            item = by_key.get(key)
            if item is None:
                continue
            if value is not None or final:
                rows[key] = {
                    "key": key,
                    "ref": item.ref,
                    "value": value,
                    "status": "ok" if value is not None else "invalid",
                    "model": settings.model,
                    "prompt_version": task.prompt_version,
                }
            else:
                retry.append((key, item))
        store.save(rows)
        return retry

    by_key: dict[str, Item] = {}
    for item in items:
        by_key.setdefault(cache_key(task, settings, item.payload), item)

    # A batch left by an interrupted run is collected first: it is already paid for.
    state_path = _state_path(task)
    if state_path.exists():
        state = json.loads(state_path.read_text("utf-8"))
        if state.get("settings") != settings.__dict__:
            raise SystemExit(
                f"Batch {state['batch_id']} from an earlier run used {state.get('settings')}. "
                f"Rerun with those settings to collect it (it is already paid for), or delete "
                f"{state_path} to abandon it."
            )
        log(f"Collecting batch {state['batch_id']} from an earlier run (already paid for).")
        client = client_factory()
        outcome = _collect(client, task, state, by_key, summary.usage, log, poll_seconds)
        record(outcome, final=False)
        summary.sent = True
        state_path.unlink()

    uncached = [(k, i) for k, i in by_key.items() if k not in rows]
    summary.cached = len(by_key) - len(uncached)
    summary.uncached = len(uncached)
    todo = uncached[: max(limit, 0)]
    if not todo:
        log(f"{summary.cached:,} items cached, 0 to send: no calls, $0.00.")
        return summary

    groups = list(_chunks([i for _, i in todo], task.group_size))
    summary.estimate = estimate(task, settings, groups, batch, prices)
    e = summary.estimate
    log(
        f"{summary.cached:,} items cached; {summary.uncached:,} not cached, sending {e.items:,} "
        f"(--limit {limit:,}) in {e.requests:,} requests to {settings.model}"
        f"{' via the Batch API' if batch else ''}.\n"
        f"Estimated {e.input_tokens:,} input and {e.output_tokens:,} output tokens: "
        f"about ${e.cost:.2f}."
    )
    if not yes:
        log("Nothing sent. Add --yes to run it.")
        return summary

    client = client_factory()
    summary.sent = True
    # Attempt 2 resends only the items whose output failed validation. Items whose request
    # errored are not resent now; they stay unstored, so the next run picks them up.
    pending = todo
    for attempt in (1, 2):
        keyed = [pending[s : s + task.group_size] for s in range(0, len(pending), task.group_size)]
        if batch:
            outcome = _send_batch(
                client, task, settings, keyed, summary.usage, log, poll_seconds, attempt
            )
            state_path.unlink(missing_ok=True)
        else:
            outcome = _send_direct(client, task, settings, keyed, summary.usage)
        pending = record(outcome, final=attempt == 2)
        if not pending:
            break
        if attempt == 1:
            log(f"Retrying {len(pending):,} items whose output failed validation.")

    done = [rows[k] for k, _ in todo if k in rows]
    summary.ok = sum(1 for r in done if r["status"] == "ok")
    summary.invalid = sum(1 for r in done if r["status"] == "invalid")
    summary.errored = sum(1 for k, _ in todo if k not in rows)
    summary.cost = summary.usage.cost(prices, batch)
    log(
        f"Done: {summary.ok:,} valid, {summary.invalid:,} invalid (stored as null), "
        f"{summary.errored:,} errored (not stored; the next run retries them). "
        f"Used {summary.usage.input_tokens:,} input and {summary.usage.output_tokens:,} output "
        f"tokens in {summary.usage.requests:,} requests: ${summary.cost:.4f}."
    )
    return summary
