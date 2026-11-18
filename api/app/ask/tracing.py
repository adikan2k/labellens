"""Langfuse tracing for the ask agent: one trace per run, a generation per model call, a span
per tool call. Off (no-ops) when LANGFUSE_* is not set.

Tracing never breaks a run: every call into Langfuse is guarded, and a failure is logged and
dropped. The client batches in the background; `flush()` sends what is pending, which the
endpoint calls after the answer is out, so it adds nothing to the user's wait.
"""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("labellens.ask.tracing")


class Observation:
    """A guarded wrapper around a Langfuse observation (or nothing, when tracing is off)."""

    def __init__(self, inner: Any | None = None):
        self.inner = inner

    def child(self, name: str, as_type: str, **fields: Any) -> Observation:
        if self.inner is None:
            return Observation()
        try:
            return Observation(self.inner.start_observation(name=name, as_type=as_type, **fields))
        except Exception:
            log.warning("Langfuse: could not start %s", name, exc_info=True)
            return Observation()

    def update(self, **fields: Any) -> None:
        if self.inner is not None:
            try:
                self.inner.update(**fields)
            except Exception:
                log.warning("Langfuse: update failed", exc_info=True)

    def end(self, **fields: Any) -> None:
        if self.inner is not None:
            try:
                if fields:
                    self.inner.update(**fields)
                self.inner.end()
            except Exception:
                log.warning("Langfuse: end failed", exc_info=True)


class Tracer:
    def __init__(self, client: Any | None = None):
        self.client = client

    @classmethod
    def from_keys(
        cls, public_key: str | None, secret_key: str | None, base_url: str | None
    ) -> Tracer:
        if not (public_key and secret_key):
            return cls()
        try:
            from langfuse import Langfuse, is_langfuse_span

            # Only our own spans: the Anthropic SDK and FastAPI emit OpenTelemetry spans too,
            # which would duplicate every model call (and its cost) and add request spans.
            client = Langfuse(
                public_key=public_key,
                secret_key=secret_key,
                base_url=base_url,
                should_export_span=is_langfuse_span,
            )
            return cls(client)
        except Exception:
            log.warning("Langfuse: could not start the client; tracing is off", exc_info=True)
            return cls()

    @property
    def enabled(self) -> bool:
        return self.client is not None

    def trace(self, name: str, **fields: Any) -> Observation:
        if self.client is None:
            return Observation()
        try:
            # A trace of its own, always sampled. Without it the run inherits the request's
            # context, and on Cloud Run that is Google's `traceparent`, sampled for only a
            # few requests: the rest of the runs were never recorded.
            own_trace = {"trace_id": self.client.create_trace_id()}
            return Observation(
                self.client.start_observation(
                    trace_context=own_trace, name=name, as_type="agent", **fields
                )
            )
        except Exception:
            log.warning("Langfuse: could not start the trace", exc_info=True)
            return Observation()

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception:
                log.warning("Langfuse: flush failed", exc_info=True)
