"""Validated business inputs, runtime-only security context and normalized tool results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agents.schemas import RetrievedEvidence


class ToolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ToolContext(ToolModel):
    """Server-injected identity. Any caller-supplied values are overwritten by ToolExecutor."""
    request_id: str
    user_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    authorized_kb_ids: list[int] = Field(default_factory=list)


class AgentRuntimeContext(ToolModel):
    request_id: str
    thread_id: str
    user_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    authorized_kb_ids: list[int] = Field(default_factory=list)
    permission_scopes: set[str] = Field(default_factory=set)
    agent_name: str
    intent: str = "unknown"
    risk_level: str = "low"
    workflow_stage: str = "unknown"
    online_search_enabled: bool = False
    remaining_tool_calls: int = Field(ge=0)
    remaining_token_budget: int = Field(ge=0)


class LocalRetrievalInput(ToolModel):
    context: ToolContext
    query: str = Field(min_length=1, max_length=4000)
    exact_terms: list[str] = Field(default_factory=list, max_length=20)
    numeric_constraints: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    population_constraints: list[str] = Field(default_factory=list, max_length=20)
    time_constraints: list[str] = Field(default_factory=list, max_length=20)
    negations: list[str] = Field(default_factory=list, max_length=20)
    # None delegates final evidence sizing to HybridRetriever's query-aware policy.
    top_k: int | None = Field(default=None, ge=1, le=100)

    @field_validator("context")
    @classmethod
    def scope_must_be_explicit(cls, value: ToolContext) -> ToolContext:
        if not value.authorized_kb_ids:
            raise ValueError("local retrieval requires non-empty authorized_kb_ids")
        return value


class OnlineRetrievalInput(ToolModel):
    context: ToolContext
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=20)


class DocumentContextInput(ToolModel):
    context: ToolContext
    chunk_id: int = Field(gt=0)
    neighboring_chunks: int = Field(default=1, ge=0, le=3)


class MedicalTableInput(ToolModel):
    context: ToolContext
    document_id: int = Field(gt=0)
    table_id: str | None = None
    query: str | None = Field(default=None, max_length=500)


class ToolError(ToolModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolUsage(ToolModel):
    latency_ms: float = 0
    cache_hit: bool = False
    result_count: int = 0
    source: str = "unknown"
    tool_version: str = "unknown"
    retries: int = 0


class ToolResult(ToolModel):
    status: Literal["success", "no_result", "partial", "error", "forbidden", "timeout", "cancelled"]
    data: Any | None = None
    evidence: list[RetrievedEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: ToolError | None = None
    usage: ToolUsage = Field(default_factory=ToolUsage)
    # Compatibility inputs. Executor always normalizes these into ``error``.
    error_code: str | None = None
    message: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_status(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            value["status"] = {"ok": "success", "degraded": "partial"}.get(value.get("status"), value.get("status"))
        return value

    @model_validator(mode="after")
    def normalize_error(self):
        if self.error is None and self.error_code:
            self.error = ToolError(code=self.error_code, message=self.message or self.error_code, retryable=self.status in {"error", "timeout"})
        if self.data is None:
            if self.evidence:
                self.data = [item.model_dump(mode="json") for item in self.evidence]
        return self


ToolExecutionResult = ToolResult


class ToolPolicyDecision(ToolModel):
    enabled: bool
    reason: str
    requires_approval: bool = False
    max_calls: int = 0
    fallback_tool: str | None = None


class ToolHealthStatus(ToolModel):
    tool_name: str
    status: Literal["healthy", "degraded", "unavailable", "disabled"]
    last_success_at: str | None = None
    error_rate_5m: float = 0
    p95_latency_ms: float = 0
    circuit_state: Literal["closed", "open", "half-open"] = "closed"
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
