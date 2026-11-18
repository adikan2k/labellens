"""POST /ask behind the route: limits, the run log, replays and the event stream.

- Rate limit: ASK_RATE_LIMIT_PER_HOUR questions per client per rolling hour, counted from
  app.ask_runs so it holds across Cloud Run instances. Checked before the stream opens; the
  route answers 429 with Retry-After.
- Daily cap: once today's (UTC) spend reaches ASK_DAILY_SPEND_CAP_USD, questions get a
  recorded example run instead (`replay: true`), the closest of the replays by shared words.
- The client is identified by a keyed hash (HMAC-SHA256) of its address, never the address.
  On Cloud Run the address is the last X-Forwarded-For entry, the one Google's front end
  appends; earlier entries are whatever the client sent.
- Every question gets a row in app.ask_runs when it starts ('running'), updated at the end
  with the outcome, tokens and cost. A client that disconnects stops the run ('cancelled').

The stream is server-sent events: `step` per tool call, then `answer` or `error`.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from api.app.ask.agent import Agent, AgentError, Answer, AskTimeout, Step
from api.app.ask.prompts import PROMPT_VERSION
from api.app.ask.tools import Tools
from api.app.db import Database, DictConnection
from api.app.embeddings import Voyage
from api.app.graph import Graph

log = logging.getLogger("labellens.ask")

REPLAY_DIR = Path(__file__).resolve().parent / "replays"
CAP_REACHED = (
    "Today's budget for live answers is used up, so this is a recorded example run. "
    "Live answers come back tomorrow (UTC)."
)
NO_REPLAY = "Today's budget for live answers is used up. Try again tomorrow (UTC)."
ERROR_MESSAGES = {
    "timeout": "That took too long, so it was stopped. Try a narrower question.",
    "tool_failed": "The data did not answer. Try again in a few seconds.",
    "internal": "Something went wrong answering that. Try again.",
}

RATE_SQL = """
select count(*) as n, min(created_at) as oldest,
       extract(epoch from (min(created_at) + interval '1 hour' - now())) as wait
from app.ask_runs
where client_hash = %s and kind = %s and created_at > now() - interval '1 hour'
"""
SPENT_SQL = """
select coalesce(sum(cost_usd), 0) as spent from app.ask_runs
where created_at >= date_trunc('day', now(), 'UTC')
"""
START_SQL = """
insert into app.ask_runs (client_hash, model, prompt_version, kind) values (%s, %s, %s, %s)
returning id
"""
FINISH_SQL = """
update app.ask_runs set outcome = %(outcome)s, input_tokens = %(input_tokens)s,
    output_tokens = %(output_tokens)s, embedding_tokens = %(embedding_tokens)s,
    cost_usd = %(cost)s, tool_calls = %(tool_calls)s, duration_ms = %(duration_ms)s,
    replay = %(replay)s, refused = %(refused)s
where id = %(id)s
"""


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def client_address(forwarded_for: str | None, peer: str | None) -> str:
    if forwarded_for:
        last = forwarded_for.split(",")[-1].strip()
        if last:
            return last
    return peer or "unknown"


def client_key(address: str) -> str:
    """One client per IPv4 address, and per IPv6 /64: a home or phone gets a whole /64 and
    rotates its address inside it, which would otherwise reset the hourly limit."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return str(ip.ipv4_mapped)
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def client_hash(key: bytes, address: str) -> str:
    return hmac.new(key, client_key(address).encode(), hashlib.sha256).hexdigest()[:32]


# --- Replays -------------------------------------------------------------------------------

_WORD = re.compile(r"[a-z0-9]{3,}")


@dataclass(frozen=True)
class Replay:
    question: str
    steps: list[dict[str, Any]]
    answer: dict[str, Any]


def load_replays(directory: Path = REPLAY_DIR) -> list[Replay]:
    replays = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text("utf-8"))
        replays.append(Replay(data["question"], data["steps"], data["answer"]))
    return replays


def choose_replay(replays: list[Replay], question: str) -> Replay | None:
    words = set(_WORD.findall(question.lower()))
    best, best_score = None, -1
    for replay in replays:
        score = len(words & set(_WORD.findall(replay.question.lower())))
        if score > best_score:
            best, best_score = replay, score
    return best


# --- The service ---------------------------------------------------------------------------


@dataclass
class AskLimits:
    per_hour: int
    daily_cap_usd: float
    timeout_seconds: float


@dataclass
class AskService:
    db: Database  # owner role: reads and writes app.ask_runs
    readonly: Database  # the read-only role, for the tools
    graph: Graph
    voyage: Voyage
    agent: Agent
    limits: AskLimits
    hash_key: bytes
    replays: list[Replay]
    snapshot: Callable[[], Any]  # the Source for the answer

    def _conn(self) -> AbstractContextManager[DictConnection]:
        return contextmanager(self.db.connection)()

    def _readonly(self) -> AbstractContextManager[DictConnection]:
        return contextmanager(self.readonly.connection)()

    def retry_after(self, who: str) -> int | None:
        """Seconds until this client may ask again, or None if it may ask now."""
        with self._conn() as conn:
            row = conn.execute(RATE_SQL, [who, "ask"]).fetchone()
        if row and row["n"] >= self.limits.per_hour:
            return max(1, int(float(row["wait"] or 0)) + 1)
        return None

    def _over_cap(self) -> bool:
        with self._conn() as conn:
            row = conn.execute(SPENT_SQL).fetchone()
        return bool(row) and float(row["spent"]) >= self.limits.daily_cap_usd  # type: ignore[index]

    def _start(self, who: str) -> int:
        with self._conn() as conn:
            row = conn.execute(START_SQL, [who, self.agent.model, PROMPT_VERSION, "ask"]).fetchone()
        assert row
        return int(row["id"])

    def _finish(self, run_id: int, **fields: Any) -> None:
        values = {
            "input_tokens": 0,
            "output_tokens": 0,
            "embedding_tokens": 0,
            "cost": 0,
            "tool_calls": 0,
            "duration_ms": None,
            "replay": False,
            "refused": False,
        }
        try:
            with self._conn() as conn:
                conn.execute(FINISH_SQL, values | fields | {"id": run_id})
        except Exception:  # the answer is out; a lost log row must not become an error
            log.warning("Could not finish ask run %s", run_id, exc_info=True)

    def stream(self, question: str, who: str) -> Iterator[str]:
        """The event stream for one question. The rate limit was checked by the caller."""
        run_id = self._start(who)
        outcome = "cancelled"
        fields: dict[str, Any] = {}
        try:
            if self._over_cap():
                outcome = "replay"
                yield from self._replay(question)
                fields = {"replay": True}
                return
            run = self.agent.run(
                question,
                Tools(self._readonly, self.graph, self.voyage),
                timeout=self.limits.timeout_seconds,
            )
            try:
                for event in run.events():
                    if isinstance(event, Step):
                        yield sse("step", event.as_dict())
                    else:
                        outcome = "refused" if event.refused else "answer"
                        yield sse("answer", self._answer(event, replay=False))
            except AskTimeout:
                outcome = "timeout"
                yield sse("error", {"code": "timeout", "message": ERROR_MESSAGES["timeout"]})
            except AgentError as error:
                outcome = error.code
                yield sse("error", {"code": error.code, "message": ERROR_MESSAGES[error.code]})
            except Exception:
                log.exception("ask run failed")
                outcome = "internal"
                yield sse("error", {"code": "internal", "message": ERROR_MESSAGES["internal"]})
            fields = {
                "input_tokens": run.usage.input_tokens,
                "output_tokens": run.usage.output_tokens,
                "embedding_tokens": run.usage.embedding_tokens,
                "cost": round(run.cost, 6),
                "tool_calls": run.tool_calls,
                "duration_ms": run.duration_ms,
                "refused": bool(run.answer and run.answer.refused),
            }
        finally:
            self._finish(run_id, outcome=outcome, **fields)
            self.agent.tracer.flush()  # after the answer is out

    def _answer(self, answer: Answer, *, replay: bool) -> dict[str, Any]:
        return {
            "text": answer.text,
            "citations": answer.citations,
            "refused": answer.refused,
            "replay": replay,
            "source": self.snapshot(),
        }

    def _replay(self, question: str) -> Iterator[str]:
        replay = choose_replay(self.replays, question)
        if replay is None:
            yield sse("answer", self._answer(Answer(NO_REPLAY, [], False), replay=True))
            return
        for step in replay.steps:
            time.sleep(0.15)  # paced like a run, so the steps read as steps
            yield sse("step", step)
        a = replay.answer
        text = f"{CAP_REACHED}\n\nExample question: {replay.question}\n\n{a['text']}"
        yield sse("answer", self._answer(Answer(text, a["citations"], a["refused"]), replay=True))
