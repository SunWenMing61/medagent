"""Strict contracts for request context and the four persisted Memory layers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


MemoryType = Literal["session", "semantic", "episodic", "procedural"]
Sensitivity = Literal["normal", "personal", "medical_sensitive", "highly_sensitive"]
MemoryStatus = Literal["active", "superseded", "disputed", "deleted", "expired"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RequestContext(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    request_id: str
    thread_id: str
    user_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    raw_query: str
    standalone_query: str | None = None
    authorized_kb_ids: list[int]
    permission_scopes: list[str]
    intent: str | None = None
    risk_level: str | None = None
    locale: str = "zh-CN"
    token_budget: int = Field(gt=0)
    tool_call_budget: int = Field(ge=0)


class ActiveEntity(StrictModel):
    entity_type: str
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    source_message_id: str
    confidence: float = Field(ge=0, le=1)
    last_mentioned_at: datetime


class UnresolvedQuestion(StrictModel):
    question_id: str
    description: str
    status: Literal["waiting_for_user", "resolved", "expired"]
    created_at: datetime
    expires_at: datetime | None = None


class SessionMemory(StrictModel):
    thread_id: str
    user_id: int
    tenant_id: int
    rolling_summary: str
    active_topic: str | None = None
    active_entities: list[ActiveEntity]
    unresolved_questions: list[UnresolvedQuestion]
    confirmed_constraints: list[dict[str, Any]]
    latest_corrections: list[dict[str, Any]] = Field(default_factory=list)
    last_updated_at: datetime


class MemoryCandidate(StrictModel):
    memory_type: MemoryType = "semantic"
    category: Literal[
        "preference", "profile", "project_context", "communication_style", "explicit_user_fact",
    ]
    subject: str = Field(min_length=1, max_length=255)
    predicate: str = Field(min_length=1, max_length=255)
    value: str | dict[str, Any]
    source_message_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    importance: float = Field(ge=0, le=1)
    reason_to_remember: str
    sensitivity: Sensitivity = "normal"
    source_type: Literal["user_explicit", "user_confirmed", "admin_import", "system_observed", "model_inferred", "external_retrieval"]
    source_role: Literal["user", "assistant", "system", "admin"]
    explicit_instruction: bool = False
    confirmed: bool = False
    expires_at: datetime | None = None

    @model_validator(mode="after")
    def semantic_only(self):
        if self.memory_type != "semantic":
            raise ValueError("Long-term fact candidates must use semantic memory")
        return self


class MemoryAccessPolicy(StrictModel):
    agent_name: str
    readable_memory_types: set[MemoryType]
    writable_memory_types: set[MemoryType]
    max_items: int = Field(ge=0, le=20)
    max_tokens: int = Field(ge=0, le=4000)
    allowed_sensitivity: set[Sensitivity]


class MemoryPolicyDecision(StrictModel):
    allowed: bool
    reason: str
    status: Literal["accept", "reject", "needs_confirmation"]


class SemanticMemoryResponse(StrictModel):
    memory_id: str
    tenant_id: int
    user_id: int | None
    namespace: str
    memory_type: MemoryType
    category: str
    subject: str
    predicate: str
    value: str | dict[str, Any]
    source_type: str
    source_message_ids: list[str]
    confidence: float
    importance: float
    sensitivity: Sensitivity
    trust_level: Literal["high", "medium", "low"]
    status: MemoryStatus
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    expires_at: datetime | None = None
    version: int
    can_support_medical_claim: Literal[False] = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RetrievedMemory(SemanticMemoryResponse):
    final_score: float = Field(ge=0, le=1)
    match_reasons: list[str] = Field(default_factory=list)


class MemoryWriteRequest(StrictModel):
    category: Literal["preference", "profile", "project_context", "communication_style", "explicit_user_fact"]
    subject: str = Field(min_length=1, max_length=255)
    predicate: str = Field(min_length=1, max_length=255)
    value: str | dict[str, Any]
    source_message_ids: list[str] = Field(default_factory=list)
    sensitivity: Sensitivity = "normal"
    expires_at: datetime | None = None


class MemoryUpdateRequest(StrictModel):
    value: str | dict[str, Any]
    sensitivity: Sensitivity | None = None
    expires_at: datetime | None = None
    reason: str = "user correction"


class MemorySearchResponse(StrictModel):
    items: list[RetrievedMemory]
    selected_tokens: int
    can_support_medical_claim: Literal[False] = False


class MemoryAuditResponse(StrictModel):
    audit_id: str
    memory_id: str | None
    operation: str
    operator_type: str
    reason: str
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    created_at: datetime | None = None


class EpisodicMemory(StrictModel):
    episode_id: str
    tenant_id: int
    user_id: int | None
    thread_id: str | None
    request_id: str | None
    event_type: Literal["user_correction", "task_completed", "task_failed", "tool_failure", "human_review", "preference_observed", "workflow_outcome"]
    task_type: str
    situation_summary: str
    action_summary: str
    outcome_summary: str
    success: bool
    quality_score: float | None = None
    related_entities: list[str]
    source_run_ids: list[str]
    reusable: bool
    expires_at: datetime | None = None
    created_at: datetime


class ProceduralMemory(StrictModel):
    procedure_id: str
    scope: Literal["global", "tenant", "agent", "task_type"]
    agent_name: str | None
    task_type: str
    trigger_conditions: dict[str, Any]
    recommended_steps: list[str]
    prohibited_actions: list[str]
    required_tools: list[str]
    fallback_strategy: list[str]
    source: Literal["developer_defined", "evaluation_derived", "human_review", "production_feedback"]
    evaluation_score: float | None = None
    version: str
    status: Literal["draft", "active", "deprecated"]
    created_at: datetime
    updated_at: datetime
