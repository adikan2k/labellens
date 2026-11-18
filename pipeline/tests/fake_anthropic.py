"""A stand-in for the Anthropic client: no network, no spend, and a record of every call.

`answer(params)` returns the response text for one request. Batch results come back in
reverse order, so code that matched results by position instead of custom_id would fail.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Block:
    text: str
    type: str = "text"


@dataclass
class FakeUsage:
    input_tokens: int = 100
    output_tokens: int = 20
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Message:
    content: list[Block]
    stop_reason: str = "end_turn"
    usage: FakeUsage = field(default_factory=FakeUsage)


@dataclass
class Counts:
    succeeded: int = 0
    processing: int = 0


@dataclass
class Batch:
    id: str
    processing_status: str = "ended"
    request_counts: Counts = field(default_factory=Counts)


@dataclass
class Result:
    type: str
    message: Message | None = None


@dataclass
class Entry:
    custom_id: str
    result: Result


class _Batches:
    def __init__(self, client: FakeAnthropic):
        self.client = client
        self.stored: dict[str, list[dict[str, Any]]] = {}

    def create(self, requests: list[dict[str, Any]]) -> Batch:
        batch_id = f"msgbatch_{len(self.stored) + 1}"
        self.stored[batch_id] = requests
        self.client.batches_created += 1
        return Batch(batch_id)

    def retrieve(self, batch_id: str) -> Batch:
        return Batch(batch_id)

    def results(self, batch_id: str) -> list[Entry]:
        entries = []
        for request in reversed(self.stored[batch_id]):
            self.client.calls.append(request["params"])
            if request["custom_id"] in self.client.error_ids:
                entries.append(Entry(request["custom_id"], Result("errored")))
                continue
            text = self.client.answer(request["params"])
            entries.append(Entry(request["custom_id"], Result("succeeded", Message([Block(text)]))))
        return entries


class _Messages:
    def __init__(self, client: FakeAnthropic):
        self.client = client
        self.batches = _Batches(client)

    def create(self, **params: Any) -> Message:
        self.client.calls.append(params)
        return Message([Block(self.client.answer(params))])


class FakeAnthropic:
    def __init__(self, answer: Callable[[dict[str, Any]], str]):
        self.answer = answer
        self.calls: list[dict[str, Any]] = []
        self.batches_created = 0
        self.error_ids: set[str] = set()
        self.messages = _Messages(self)
