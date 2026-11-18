"""The ask agent: a small tool-use loop on the Anthropic Messages API, no framework.

One run: the question goes to the model (model_default, Haiku 5.5) with the system prompt and
tool definitions of PROMPT_VERSION. Each tool call the model makes is run and yielded as a
Step as soon as it finishes, so the endpoint can stream it. After MAX_TOOL_CALLS calls the
next request sends tool_choice none, so the model has to answer with what it has.

The answer cites tool results by the ids the tools handed out ([R2], [N1, E3]). Those become
numbered citations with app links; an id no tool returned is dropped from the text, so the
model cannot cite something it never looked up. A reply that starts with REFUSAL_MARKER is a
refusal of medical or dietary advice: the marker is removed and `refused` is set.

Thinking is off: these are short lookups where latency matters more, and Haiku 5.5 accepts
thinking off at the default effort.

Prompt caching: the system prompt is one text block with an ephemeral cache_control marker.
Tools render before the system prompt, so that one marker caches the tool definitions and the
system prompt together (about 2,200 tokens, over Haiku 5.5's 512-token minimum). Every later
call of the run, and of any run within the 5-minute TTL, reads that prefix at a tenth of the
input price instead of paying for it again. tool_choice switching to none does not break it.
See evals/results/ask_caching.md for the measured effect.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from typing import Any

import psycopg
from psycopg_pool import PoolTimeout

from api.app.ask.prompts import PROMPT_VERSION, REFUSAL_MARKER, TOOL_DEFINITIONS, system_prompt
from api.app.ask.tools import TOOL_NAMES, Citations, Tools
from api.app.ask.tracing import Tracer
from api.app.config import embedding_price_per_mtok, input_cost_usd, price_per_mtok

MAX_TOOL_CALLS = 6
MAX_TURNS = MAX_TOOL_CALLS + 2  # parallel calls can use the budget in fewer turns
MAX_TOKENS = 1500
MAX_CALL_SECONDS = 25.0  # one model call; the run's deadline caps it further
_CITE_GROUP = re.compile(r"\[([RNE]\d+(?:\s*,\s*[RNE]\d+)*)\]")
BUDGET_USED = '{"error":"The tool budget for this question is used up. Answer with what you have."}'
TURNS_USED = "I couldn't finish looking this up. Try a narrower question."


class AskTimeout(Exception):
    """The run passed its deadline."""


class AgentError(Exception):
    """The run cannot finish: `code` is the contract's AskError code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Step:
    index: int
    tool: str
    summary: str
    row_count: int
    duration_ms: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Answer:
    text: str
    citations: list[dict[str, Any]]
    refused: bool


@dataclass
class Usage:
    """Token counts for a run. input_tokens is every input token, cached or not; the two cache
    counts say how many of them were read from or written to the prompt cache."""

    input_tokens: int = 0
    output_tokens: int = 0
    embedding_tokens: int = 0
    model_calls: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    @property
    def uncached_input_tokens(self) -> int:
        return self.input_tokens - self.cache_read_input_tokens - self.cache_creation_input_tokens

    def cost(self, model: str, embeddings_model: str) -> float:
        _, price_out = price_per_mtok(model)
        embed = embedding_price_per_mtok(embeddings_model)
        cost_in = input_cost_usd(
            model,
            self.uncached_input_tokens,
            self.cache_read_input_tokens,
            self.cache_creation_input_tokens,
        )
        return cost_in + (self.output_tokens * price_out + self.embedding_tokens * embed) / 1e6


def finalize(text: str, citations: Citations) -> Answer:
    """Strip the refusal marker, number the citations, drop ids no tool returned."""
    text = text.strip()
    refused = text.startswith(REFUSAL_MARKER)
    if refused:
        text = text[len(REFUSAL_MARKER) :].strip()
    numbers: dict[str, int] = {}
    out: list[dict[str, Any]] = []

    def number(match: re.Match[str]) -> str:
        parts = []
        for cite_id in re.split(r"\s*,\s*", match.group(1)):
            cite = citations.get(cite_id)
            if cite is None:
                continue  # not handed out by any tool: invented, so dropped
            if cite_id not in numbers:
                numbers[cite_id] = len(numbers) + 1
                out.append(
                    {
                        "n": numbers[cite_id],
                        "kind": cite.kind,
                        "ref": cite.ref,
                        "label": cite.label,
                        "url": cite.url,
                    }
                )
            parts.append(f"[{numbers[cite_id]}]")
        return "".join(parts)

    text = _CITE_GROUP.sub(number, text)
    text = re.sub(r"[ \t]+([.,;:)])", r"\1", text)  # space left where an id was dropped
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    return Answer(text, out, refused)


def _block(block: Any) -> dict[str, Any]:
    kind = getattr(block, "type", None)
    if kind == "text":
        return {"type": "text", "text": block.text}
    if kind == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return dict(vars(block))


@dataclass
class Agent:
    client: Any  # anthropic.Anthropic, or a fake in tests
    model: str
    embeddings_model: str
    tracer: Tracer = field(default_factory=Tracer)
    tool_names: tuple[str, ...] = TOOL_NAMES
    max_tool_calls: int = MAX_TOOL_CALLS
    name: str = "ask"
    cache_prompt: bool = True  # off only to measure the difference (scripts/measure_ask_caching.py)

    def run(self, question: str, tools: Tools, *, timeout: float | None = None) -> Run:
        deadline = time.monotonic() + timeout if timeout else None
        return Run(self, question, tools, deadline)


@dataclass
class Run:
    agent: Agent
    question: str
    tools: Tools
    deadline: float | None
    steps: list[Step] = field(default_factory=list)
    answer: Answer | None = None
    usage: Usage = field(default_factory=Usage)
    tool_calls: int = 0
    started: float = field(default_factory=time.perf_counter)

    @property
    def cost(self) -> float:
        return self.usage.cost(self.agent.model, self.agent.embeddings_model)

    @property
    def duration_ms(self) -> int:
        return round((time.perf_counter() - self.started) * 1000)

    def _check_deadline(self) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise AskTimeout()

    def events(self) -> Iterator[Step | Answer]:
        agent = self.agent
        trace = agent.tracer.trace(
            agent.name,
            input={"question": self.question},
            metadata={
                "prompt_version": PROMPT_VERSION,
                "model": agent.model,
                "tools": list(agent.tool_names),
            },
        )
        system: str | list[dict[str, Any]] = system_prompt(agent.tool_names)
        if agent.cache_prompt:
            system = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        definitions = [TOOL_DEFINITIONS[name] for name in agent.tool_names]
        messages: list[dict[str, Any]] = [{"role": "user", "content": self.question}]
        try:
            for _ in range(MAX_TURNS):
                self._check_deadline()
                force_answer = self.tool_calls >= agent.max_tool_calls
                params: dict[str, Any] = {
                    "model": agent.model,
                    "max_tokens": MAX_TOKENS,
                    "system": system,
                    "messages": messages,
                    "tools": definitions,
                    "tool_choice": {"type": "none" if force_answer else "auto"},
                    "thinking": {"type": "disabled"},
                }
                generation = trace.child(
                    "model call",
                    "generation",
                    model=agent.model,
                    input=list(messages),
                    model_parameters={
                        "max_tokens": MAX_TOKENS,
                        "tool_choice": params["tool_choice"]["type"],
                    },
                )
                response = self._create(params)
                usage = response.usage
                uncached = usage.input_tokens
                cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
                cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
                self.usage.input_tokens += uncached + cache_read + cache_write
                self.usage.cache_read_input_tokens += cache_read
                self.usage.cache_creation_input_tokens += cache_write
                self.usage.output_tokens += usage.output_tokens
                self.usage.model_calls += 1
                content = [_block(b) for b in response.content]
                _, price_out = price_per_mtok(agent.model)
                cost = {
                    "input": input_cost_usd(agent.model, uncached),
                    "input_cache_read": input_cost_usd(agent.model, 0, cache_read=cache_read),
                    "input_cache_creation": input_cost_usd(agent.model, 0, cache_write=cache_write),
                    "output": usage.output_tokens * price_out / 1e6,
                }
                generation.end(
                    output=content,
                    usage_details={
                        "input": uncached,
                        "input_cache_read": cache_read,
                        "input_cache_creation": cache_write,
                        "output": usage.output_tokens,
                    },
                    cost_details=cost | {"total": sum(cost.values())},
                    metadata={"stop_reason": response.stop_reason},
                )

                if response.stop_reason == "refusal":
                    self.answer = Answer(
                        "LabelLens can't help with that. Ask about the labels of US food "
                        "products: nutrients, Nutri-Score, ingredients or additives.",
                        [],
                        True,
                    )
                    break
                uses = [b for b in content if b["type"] == "tool_use"]
                if response.stop_reason == "tool_use" and uses and not force_answer:
                    messages.append({"role": "assistant", "content": content})
                    results = []
                    for use in uses:
                        block, step = self._call(use, trace)
                        results.append(block)
                        if step is not None:
                            yield step
                    messages.append({"role": "user", "content": results})
                    continue
                text = "".join(b["text"] for b in content if b["type"] == "text")
                self.answer = finalize(text, self.tools.citations)
                break
            else:
                self.answer = Answer(TURNS_USED, [], False)
        except Exception as error:
            trace.end(level="ERROR", status_message=type(error).__name__, metadata=self._summary())
            raise
        trace.end(
            output={
                "text": self.answer.text,
                "refused": self.answer.refused,
                "citations": self.answer.citations,
            },
            metadata=self._summary(),
        )
        yield self.answer

    def _summary(self) -> dict[str, Any]:
        return {
            "prompt_version": PROMPT_VERSION,
            "model": self.agent.model,
            "tool_calls": self.tool_calls,
            "cost_usd": round(self.cost, 6),
            "duration_ms": self.duration_ms,
            **asdict(self.usage),
        }

    def _create(self, params: dict[str, Any]) -> Any:
        import anthropic

        if self.deadline is not None:  # never wait past the run's deadline
            remaining = self.deadline - time.monotonic()
            params = params | {"timeout": max(1.0, min(MAX_CALL_SECONDS, remaining))}
        try:
            return self.agent.client.messages.create(**params)
        except anthropic.APIError as error:
            raise AgentError(
                "internal", f"The model call failed: {type(error).__name__}"
            ) from error

    def _call(self, use: dict[str, Any], trace: Any) -> tuple[dict[str, Any], Step | None]:
        """Run one tool call, or refuse it over budget: its tool_result block and its step."""
        if self.tool_calls >= self.agent.max_tool_calls:
            return {
                "type": "tool_result",
                "tool_use_id": use["id"],
                "content": BUDGET_USED,
                "is_error": True,
            }, None
        self._check_deadline()
        self.tool_calls += 1
        span = trace.child(use["name"], "tool", input=use["input"])
        try:
            result = self.tools.run(use["name"], use["input"])
        except (psycopg.Error, PoolTimeout) as error:
            span.end(level="ERROR", status_message=type(error).__name__)
            raise AgentError("tool_failed", "The database did not answer. Try again.") from error
        span.end(
            output=result.content[:4000],
            level="WARNING" if result.is_error else None,
            metadata={"row_count": result.row_count, "duration_ms": result.duration_ms},
        )
        self.usage.embedding_tokens += result.embedding_tokens
        step = Step(
            self.tool_calls, result.tool, result.summary, result.row_count, result.duration_ms
        )
        self.steps.append(step)
        return {
            "type": "tool_result",
            "tool_use_id": use["id"],
            "content": result.content,
            "is_error": result.is_error,
        }, step
