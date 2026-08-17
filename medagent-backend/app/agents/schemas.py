"""Versioned, validated input/output contracts for every semantic agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Intent = Literal[
    "general_knowledge",
    "medical_knowledge",
    "symptom_consultation",
    "drug_information",
    "literature_search",
    "document_summary",
    "emergency_risk",
    "out_of_scope",
]
RetrievalRoute = Literal[
    "local_knowledge_base",
    "web_search",
    "pubmed",
    "fda_drug_label",
    "msd_manual",
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class InputTriageResult(StrictModel):
    schema_version: str = "triage-v1"
    intent: Intent
    risk_level: Literal["low", "medium", "high", "emergency"]
    need_emergency_response: bool
    need_clarification: bool
    clarification_topics: list[str] = Field(default_factory=list, max_length=3)
    required_routes: list[Literal[
        "local_rag", "online_web", "online_medical_source", "document_summary"
    ]] = Field(default_factory=list)
    medical_entities: list[dict[str, Any]] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    reason: str


class ClarificationResult(StrictModel):
    schema_version: str = "clarification-v1"
    need_clarification: bool
    missing_fields: list[str] = Field(default_factory=list)
    priority: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list, max_length=3)
    reason: str


class MedicalEntity(StrictModel):
    entity_type: Literal[
        "disease", "drug", "symptom", "lab_indicator", "procedure",
        "population", "time", "numeric_constraint", "medical_code", "other",
    ]
    original_text: str
    canonical_name: str | None = None
    synonyms: list[str] = Field(default_factory=list)
    value: str | float | None = None
    unit: str | None = None
    aliases: list[str] = Field(default_factory=list)


class RetrievalPlan(StrictModel):
    schema_version: str = "retrieval-plan-v1"
    original_query: str
    normalized_query: str
    intent: Intent = "medical_knowledge"
    standalone_query: str | None = None
    entities: list[MedicalEntity] = Field(default_factory=list)
    local_queries: list[str] = Field(default_factory=list)
    online_queries: list[str] = Field(default_factory=list)
    retrieval_routes: list[RetrievalRoute] = Field(default_factory=list)
    need_exact_match: bool = False
    need_recency_filter: bool = False
    need_guideline_priority: bool = False
    max_candidates_per_route: int = Field(default=20, ge=1, le=100)
    reason: str
    synonyms: dict[str, list[str]] = Field(default_factory=dict)
    numeric_constraints: list[dict[str, Any]] = Field(default_factory=list)
    population_constraints: list[str] = Field(default_factory=list)
    time_constraints: list[str] = Field(default_factory=list)
    negations: list[str] = Field(default_factory=list)
    referenced_memory_ids: list[str] = Field(default_factory=list)
    sub_questions: list[dict[str, Any]] = Field(default_factory=list, max_length=5)

    @field_validator("normalized_query")
    @classmethod
    def normalized_query_must_not_be_empty(cls, value: str) -> str:
        if not value:
            raise ValueError("normalized_query cannot be empty")
        return value


class EvidenceItem(StrictModel):
    evidence_id: str
    content: str
    source_type: str
    source_name: str
    document_id: str | int | None = None
    chunk_id: str | int | None = None
    page_num: int | None = None
    page_start: int | None = None
    page_end: int | None = None
    parent_chunk_id: str | int | None = None
    section_path: list[str] = Field(default_factory=list)
    section_title: str | None = None
    url: str | None = None
    pmid: str | None = None
    publication_date: str | None = None
    updated_at: str | None = None
    retrieval_score: float | None = None
    rerank_score: float | None = None
    authority_level: int = Field(default=1, ge=0, le=10)
    is_authorized: bool
    is_conversation_memory: bool
    can_support_medical_claim: bool = True
    quality_status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedEvidence(EvidenceItem):
    dense_score: float | None = None
    sparse_score: float | None = None
    exact_match_score: float | None = None
    exact_score: float | None = None
    rrf_score: float | None = None


class OnlineMedicalEvidence(StrictModel):
    evidence_id: str
    source_type: str
    source_name: str
    title: str
    content: str
    url: str | None = None
    pmid: str | None = None
    publication_date: str | None = None
    retrieved_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    authority_level: int = Field(default=5, ge=0, le=10)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceVerificationResult(StrictModel):
    schema_version: str = "evidence-verification-v1"
    evidence_status: Literal["sufficient", "insufficient", "conflicting", "unsafe", "system_error"]
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    rejected_evidence_ids: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    conflict_summary: str | None = None
    recommended_action: Literal[
        "generate_answer", "retrieve_again", "ask_user", "refuse_answer",
        "show_conflict", "human_review",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class ClaimWithEvidence(StrictModel):
    claim: str
    citation_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)


class StructuredAnswer(StrictModel):
    schema_version: str = "answer-v1"
    summary: str
    details: list[ClaimWithEvidence] = Field(default_factory=list)
    uncertainty: str | None = None
    limitations: list[str] = Field(default_factory=list)
    recommended_next_step: str | None = None
    needs_professional_consultation: bool = False


class SafetyReviewResult(StrictModel):
    schema_version: str = "safety-review-v1"
    safety_status: Literal["pass", "rewrite_required", "human_review_required", "blocked"]
    risk_categories: list[str] = Field(default_factory=list)
    unsafe_spans: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    rewrite_instructions: list[str] = Field(default_factory=list)
    final_disclaimer_required: bool = False
    reason: str


class SupervisorDecision(StrictModel):
    schema_version: str = "supervisor-v1"
    next_node: Literal[
        "triage", "clarification", "query_understanding", "retrieval",
        "evidence_verification", "answer_generation", "output_safety",
        "human_review", "finalize", "end",
    ]
    reason: str


class AgentError(StrictModel):
    agent_name: str
    error_code: str
    message: str
    retryable: bool
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    details: dict[str, Any] = Field(default_factory=dict)
