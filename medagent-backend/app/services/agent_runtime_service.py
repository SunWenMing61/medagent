"""Bounded execution runtime for all semantic agents and deterministic tools."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from pydantic import BaseModel

import app.agents  # noqa: F401 - populates the explicit registry
import app.tools  # noqa: F401 - populates the explicit registry
from app.agents.registry import agent_registry
from app.agents.schemas import AgentError
from app.core.config import settings
from app.services.checkpoint_service import checkpoint_service
from app.services.trace_service import trace_service
from app.tools.registry import tool_registry
from app.tools.executor import ToolExecutor
from app.tools.schemas import AgentRuntimeContext
from app.services.tool_governance_service import tool_governance_service


class AgentLimitExceeded(RuntimeError):
    pass


class ToolLimitExceeded(RuntimeError):
    pass


class AgentRuntimeService:
    def __init__(self, *, persist: bool = True, trace: bool = True) -> None:
        self.persist = persist
        self.trace = trace
        self.started_at = time.monotonic()
        self._tool_cache: dict[str, Any] = {}
        self.tool_executor = ToolExecutor(tool_registry)
        self._lock = threading.RLock()

    def _check_timeout(self) -> None:
        if time.monotonic() - self.started_at > settings.AGENT_TOTAL_TIMEOUT_SECONDS:
            raise TimeoutError("AGENT_TOTAL_TIMEOUT")

    def run_agent(self, state: dict, name: str, function: Callable[..., Any], *args, **kwargs) -> BaseModel:
        self._check_timeout()
        calls = int(state.get("agent_call_count", 0)) + 1
        if calls > settings.AGENT_MAX_CALLS:
            self.add_error(state, name, "AGENT_LIMIT_EXCEEDED", "Maximum agent calls exceeded", False)
            raise AgentLimitExceeded("AGENT_LIMIT_EXCEEDED")
        state["agent_call_count"] = calls
        definition, _ = agent_registry.get(name)
        started = time.perf_counter()
        try:
            output = definition.output_schema.model_validate(function(*args, **kwargs))
            status = "success"
            error_code = None
            return output
        except Exception as exc:
            status = "error"
            error_code = "AGENT_EXECUTION_ERROR"
            self.add_error(state, name, error_code, str(exc), False)
            raise
        finally:
            latency = round((time.perf_counter() - started) * 1000, 3)
            self.public_event(state, "agent_completed", {"agent": name, "status": status, "latency_ms": latency})
            if self.persist and self.trace:
                trace_service.agent(
                    request_id=state["request_id"],
                    agent_name=name,
                    agent_version=definition.version,
                    prompt_version=definition.prompt_version,
                    model=(
                        getattr(settings, definition.model_setting, settings.DEFAULT_AGENT_MODEL)
                        if definition.uses_model
                        else "deterministic-rule-v1"
                    ),
                    status=status,
                    latency_ms=latency,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    error_code=error_code,
                    trace_summary={"state_version": state.get("state_version")},
                )

    def run_tool(self, state: dict, name: str, payload: BaseModel | dict):
        self._check_timeout()
        definition, implementation = tool_registry.get(name)
        del implementation
        calls = int(state.get("tool_call_count", 0))
        if calls >= settings.TOOL_MAX_CALLS:
            self.add_error(state, name, "TOOL_LIMIT_EXCEEDED", "Maximum tool calls exceeded", False)
            raise ToolLimitExceeded("TOOL_LIMIT_EXCEEDED")
        permission_scopes = set(state.get("permission_scopes", []))
        if state.get("authorized_kb_ids"):
            permission_scopes.add("kb:read")
        permission_scopes.add("memory:read")
        general_web_enabled = bool(
            settings.ENABLE_GENERAL_WEB_SEARCH
            and state.get("assistant_profile") == "general_qa"
        )
        if settings.ENABLE_ONLINE_MEDICAL_SEARCH or general_web_enabled:
            permission_scopes.add("online:read")
        context = AgentRuntimeContext(
            request_id=state["request_id"],
            thread_id=state.get("thread_id") or state["request_id"],
            user_id=state["user_id"],
            tenant_id=state["tenant_id"],
            authorized_kb_ids=state.get("authorized_kb_ids", []),
            permission_scopes=permission_scopes,
            agent_name=state.get("current_agent", "supervisor"),
            intent=state.get("intent", "unknown"),
            risk_level=state.get("risk_level", "low"),
            workflow_stage=state.get("current_agent", "unknown"),
            online_search_enabled=bool(settings.ENABLE_ONLINE_MEDICAL_SEARCH or general_web_enabled),
            remaining_tool_calls=settings.TOOL_MAX_CALLS - calls,
            remaining_token_budget=max(0, settings.AGENT_TOKEN_BUDGET - int(state.get("tokens_used", 0))),
        )
        started = time.perf_counter()
        digest = ""
        status = "error"
        error_code = None
        try:
            result, digest = self.tool_executor.execute(name, payload, context)
            state.setdefault("tool_call_names", []).append(name)
            if result.usage.cache_hit:
                self.public_event(state, "duplicate_tool_call", {"tool": name, "cached": True})
                return result
            with self._lock:
                state["tool_call_count"] = calls + 1
                state.setdefault("tool_call_hashes", []).append(digest)
            status = result.status
            error_code = result.error.code if result.error else result.error_code
            if status in {"error", "timeout", "forbidden"}:
                state["tool_failure_count"] = int(state.get("tool_failure_count", 0)) + 1
            return result
        finally:
            latency = round((time.perf_counter() - started) * 1000, 3)
            self.public_event(state, "tool_completed", {"tool": name, "latency_ms": latency})
            if self.persist and self.trace:
                trace_service.tool(
                    request_id=state["request_id"],
                    tool_name=name,
                    arguments_hash=digest,
                    status=status,
                    latency_ms=latency,
                    error_code=error_code,
                    result_count=getattr(getattr(locals().get("result"), "usage", None), "result_count", 0),
                )
                if "result" in locals() and "digest" in locals():
                    tool_governance_service.record(
                        state=state,
                        definition=definition,
                        digest=digest,
                        result=result,
                        policy_decision=self.tool_executor.policy_decision(digest),
                    )

    def checkpoint(self, state: dict, node_name: str) -> None:
        state["updated_at"] = datetime.now(timezone.utc).isoformat()
        if self.persist:
            checkpoint_service.save(state, node_name)

    @staticmethod
    def public_event(state: dict, event_type: str, payload: dict | None = None) -> None:
        event = {"type": event_type, "timestamp": datetime.now(timezone.utc).isoformat()}
        event.update(payload or {})
        state.setdefault("public_events", []).append(event)

    @staticmethod
    def add_error(
        state: dict,
        agent_name: str,
        error_code: str,
        message: str,
        retryable: bool,
        details: dict | None = None,
    ) -> None:
        error = AgentError(
            agent_name=agent_name,
            error_code=error_code,
            message=message[:1000],
            retryable=retryable,
            details=details or {},
        )
        state.setdefault("errors", []).append(error.model_dump(mode="json"))
