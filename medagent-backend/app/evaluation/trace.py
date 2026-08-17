"""Async-safe evaluation trace collection with automatic redaction."""

from __future__ import annotations

import contextvars
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


_collector: contextvars.ContextVar["TraceCollector | None"] = contextvars.ContextVar("evaluation_trace", default=None)
_SENSITIVE = re.compile(r"\b(?:\d{15,18}[0-9Xx]?|1[3-9]\d{9}|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})\b")


def redact(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return redact(value.model_dump(mode="json"))
    if isinstance(value, str):
        return _SENSITIVE.sub("[REDACTED]", value)[:12000]
    if isinstance(value, dict):
        return {str(k): redact(v) for k, v in value.items() if str(k).lower() not in {"api_key", "authorization", "password"}}
    if isinstance(value, (list, tuple, set)):
        return [redact(item) for item in list(value)[:100]]
    return value


@dataclass
class TraceCollector:
    steps: list[dict[str, Any]] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    retrievals: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: list[dict[str, Any]] = field(default_factory=list)

    def step(self, agent: str, action: str, *, input_data: Any = None, output_data: Any = None, latency_ms: float = 0, status: str = "success") -> None:
        self.steps.append({"step_number": len(self.steps) + 1, "agent_name": agent, "action": action, "input": redact(input_data), "output": redact(output_data), "latency_ms": round(latency_ms, 3), "status": status})


@contextmanager
def trace_scope() -> Iterator[TraceCollector]:
    collector = TraceCollector()
    token = _collector.set(collector)
    try:
        yield collector
    finally:
        _collector.reset(token)


def traced_call(agent: str, action: str, function, *args, **kwargs):
    started = time.perf_counter()
    status, output = "success", None
    try:
        output = function(*args, **kwargs)
        return output
    except Exception:
        status = "error"
        raise
    finally:
        active = _collector.get()
        if active:
            rendered = output.model_dump(mode="json") if hasattr(output, "model_dump") else output
            active.step(agent, action, input_data={"args": args, "kwargs": kwargs}, output_data=rendered, latency_ms=(time.perf_counter() - started) * 1000, status=status)
