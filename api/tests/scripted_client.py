"""A scripted stand-in for anthropic.Anthropic's Messages API, for the ask agent's tests.

Each `create` call records its params and returns the next scripted message. Helpers build
the two kinds of reply the agent sees: tool calls and a final text.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any]
    type: str = "tool_use"


@dataclass
class Usage:
    input_tokens: int = 1000
    output_tokens: int = 100
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class Message:
    content: list[Any]
    stop_reason: str
    usage: Usage = field(default_factory=Usage)


def tool_calls(*calls: tuple[str, dict[str, Any]], usage: Usage | None = None) -> Message:
    blocks = [ToolUseBlock(f"toolu_{i}_{name}", name, args) for i, (name, args) in
              enumerate(calls)]  # fmt: skip
    return Message(blocks, "tool_use", usage or Usage())


def text(reply: str, *, stop_reason: str = "end_turn", usage: Usage | None = None) -> Message:
    return Message([TextBlock(reply)], stop_reason, usage or Usage())


class _Messages:
    def __init__(self, client: ScriptedClient):
        self.client = client

    def create(self, **params: Any) -> Message:
        self.client.calls.append(copy.deepcopy(params))
        if self.client.error is not None:
            raise self.client.error
        if not self.client.script:
            raise AssertionError("the agent made more model calls than scripted")
        return self.client.script.pop(0)


class ScriptedClient:
    def __init__(self, *script: Message, error: Exception | None = None):
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []
        self.error = error
        self.messages = _Messages(self)
