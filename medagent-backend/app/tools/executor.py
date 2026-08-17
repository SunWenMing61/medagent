"""Single execution gateway for validation, policy, retry, timeout, cache and circuit state."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from typing import Any

from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.tools.health import tool_health_manager
from app.tools.policy import tool_policy_engine
from app.tools.registry import ToolRegistry, tool_registry
from app.tools.schemas import AgentRuntimeContext, ToolContext, ToolError, ToolResult, ToolUsage


class ToolExecutor:
    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or tool_registry
        self._cache: dict[str, tuple[float, ToolResult]] = {}
        self._call_counts: dict[str, int] = {}
        self._policy_decisions: dict[str, Any] = {}
        self._lock = threading.RLock()

    @staticmethod
    def _injected_payload(payload: BaseModel | dict, runtime: AgentRuntimeContext) -> dict:
        raw = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
        raw["context"] = ToolContext(
            request_id=runtime.request_id,
            user_id=runtime.user_id,
            tenant_id=runtime.tenant_id,
            authorized_kb_ids=runtime.authorized_kb_ids,
        ).model_dump(mode="json")
        return raw

    @staticmethod
    def arguments_hash(name: str, normalized: dict, runtime: AgentRuntimeContext) -> str:
        material = {
            "tool": name, "arguments": normalized, "user_id": runtime.user_id,
            "tenant_id": runtime.tenant_id, "request_id": runtime.request_id,
        }
        return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def execute(self, name: str, payload: BaseModel | dict, runtime: AgentRuntimeContext) -> tuple[ToolResult, str]:
        definition, implementation = self.registry.get(name)
        try:
            validated = definition.input_schema.model_validate(self._injected_payload(payload, runtime))
        except ValidationError as exc:
            result = ToolResult(
                status="error", error=ToolError(code="TOOL_INPUT_INVALID", message=str(exc), retryable=False),
                usage=ToolUsage(source=name, tool_version=definition.version),
            )
            return result, ""
        normalized = validated.model_dump(mode="json")
        digest = self.arguments_hash(name, normalized, runtime)
        with self._lock:
            calls = self._call_counts.get(name, 0)
        health = tool_health_manager.status(name)
        decision = tool_policy_engine.decide(definition, runtime, health, calls_for_tool=calls)
        with self._lock:
            self._policy_decisions[digest] = decision
        if not decision.enabled:
            status = "forbidden" if health.circuit_state != "open" else "error"
            code = "TOOL_APPROVAL_REQUIRED" if decision.requires_approval else ("TOOL_CIRCUIT_OPEN" if health.circuit_state == "open" else "TOOL_POLICY_DENIED")
            return ToolResult(
                status=status,
                error=ToolError(code=code, message=decision.reason, retryable=health.circuit_state == "open"),
                usage=ToolUsage(source=name, tool_version=definition.version),
            ), digest

        now = time.monotonic()
        if settings.TOOL_ENABLE_CACHE and definition.cache_ttl_seconds:
            with self._lock:
                cached = self._cache.get(digest)
            if cached and cached[0] > now:
                result = cached[1].model_copy(deep=True)
                result.usage.cache_hit = True
                return result, digest

        with self._lock:
            self._call_counts[name] = calls + 1
        started = time.perf_counter()
        retries = 0
        result: ToolResult | None = None
        while retries <= definition.max_retries:
            pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"tool-{name}")
            future = pool.submit(implementation.execute, validated)
            try:
                raw_result = future.result(timeout=definition.timeout_seconds or settings.TOOL_DEFAULT_TIMEOUT)
                result = ToolResult.model_validate(raw_result)
            except FutureTimeout:
                future.cancel()
                result = ToolResult(
                    status="timeout",
                    error=ToolError(code="TOOL_TIMEOUT", message=f"{name} exceeded {definition.timeout_seconds}s", retryable=True),
                )
            except Exception as exc:
                result = ToolResult(
                    status="error",
                    error=ToolError(code="TOOL_EXECUTION_ERROR", message=str(exc)[:1000], retryable=True),
                )
            finally:
                pool.shutdown(wait=False, cancel_futures=True)
            if result.status not in {"error", "timeout"} or retries >= definition.max_retries or not (result.error and result.error.retryable):
                break
            retries += 1

        latency = round((time.perf_counter() - started) * 1000, 3)
        assert result is not None
        result.usage = ToolUsage(
            latency_ms=latency,
            cache_hit=False,
            result_count=len(result.evidence) or (len(result.data) if isinstance(result.data, list) else int(result.data is not None)),
            source=name,
            tool_version=definition.version,
            retries=retries,
        )
        success = result.status in {"success", "no_result", "partial"}
        tool_health_manager.record(name, success, latency)
        if success and settings.TOOL_ENABLE_CACHE and definition.cache_ttl_seconds:
            with self._lock:
                self._cache[digest] = (now + definition.cache_ttl_seconds, result.model_copy(deep=True))
        return result, digest

    def policy_decision(self, digest: str):
        with self._lock:
            return self._policy_decisions.get(digest)
