"""In-process health and circuit-breaker state; durable snapshots are optional."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from app.core.config import settings
from app.tools.schemas import ToolHealthStatus


class ToolHealthManager:
    def __init__(self) -> None:
        self._events = defaultdict(lambda: deque(maxlen=200))
        self._failures = defaultdict(int)
        self._opened_at: dict[str, float] = {}
        self._disabled: set[str] = set()

    def disable(self, name: str, disabled: bool = True) -> None:
        self._disabled.add(name) if disabled else self._disabled.discard(name)

    def status(self, name: str) -> ToolHealthStatus:
        if name in self._disabled:
            return ToolHealthStatus(tool_name=name, status="disabled", circuit_state="open")
        opened = self._opened_at.get(name)
        circuit = "closed"
        if opened is not None:
            if time.monotonic() - opened >= settings.TOOL_CIRCUIT_RESET_SECONDS:
                circuit = "half-open"
            else:
                circuit = "open"
        events = list(self._events[name])
        latencies = sorted(item[1] for item in events)
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0
        errors = sum(not item[0] for item in events)
        last_success = next((item[2] for item in reversed(events) if item[0]), None)
        status = "unavailable" if circuit == "open" else ("degraded" if events and errors / len(events) > 0.2 else "healthy")
        return ToolHealthStatus(
            tool_name=name, status=status, last_success_at=last_success,
            error_rate_5m=errors / len(events) if events else 0, p95_latency_ms=p95, circuit_state=circuit,
        )

    def record(self, name: str, success: bool, latency_ms: float) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._events[name].append((success, latency_ms, now))
        if success:
            self._failures[name] = 0
            self._opened_at.pop(name, None)
        else:
            self._failures[name] += 1
            if settings.TOOL_ENABLE_CIRCUIT_BREAKER and self._failures[name] >= settings.TOOL_CIRCUIT_FAILURE_THRESHOLD:
                self._opened_at[name] = time.monotonic()


tool_health_manager = ToolHealthManager()
