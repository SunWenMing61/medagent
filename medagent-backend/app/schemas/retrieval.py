"""Unified query-understanding, retrieval, constraint and sufficiency contracts."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NumericConstraint(StrictModel):
    name: str
    operator: Literal["=", "<", "<=", ">", ">=", "range"]
    value: float | list[float]
    unit: str | None = None
    original_text: str


class QueryMedicalEntity(StrictModel):
    entity_type: Literal["drug", "disease", "symptom", "lab_indicator", "population", "time", "procedure", "medical_code", "other"]
    original_text: str
    canonical_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class SubQuestion(StrictModel):
    sub_question_id: str
    question: str
    target_entities: list[str] = Field(default_factory=list)
    required_sources: list[str] = Field(default_factory=list)
    required_constraints: list[str] = Field(default_factory=list)


class QueryUnderstandingResult(StrictModel):
    original_query: str
    standalone_query: str
    normalized_query: str
    entities: list[QueryMedicalEntity] = Field(default_factory=list)
    synonyms: dict[str, list[str]] = Field(default_factory=dict)
    numeric_constraints: list[NumericConstraint] = Field(default_factory=list)
    population_constraints: list[str] = Field(default_factory=list)
    time_constraints: list[str] = Field(default_factory=list)
    negations: list[str] = Field(default_factory=list)
    referenced_memory_ids: list[str] = Field(default_factory=list)
    sub_questions: list[SubQuestion] = Field(default_factory=list, max_length=5)
    rewrite_reason: str | None = None


class RetrievalContext(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    request_id: str
    user_id: int = Field(gt=0)
    tenant_id: int = Field(gt=0)
    authorized_kb_ids: list[int]
    permission_tags: list[str] = Field(default_factory=list)
    allowed_sources: list[str] = Field(default_factory=lambda: ["local_knowledge_base"])


class RetrievalError(StrictModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class UnifiedRetrievedEvidence(StrictModel):
    evidence_id: str
    content: str
    source_type: str
    source_name: str
    document_id: int | None = None
    chunk_id: str | int | None = None
    parent_chunk_id: str | int | None = None
    page_start: int | None = None
    page_end: int | None = None
    section_path: list[str] = Field(default_factory=list)
    url: str | None = None
    pmid: str | None = None
    publication_date: date | None = None
    document_version: str | None = None
    dense_score: float | None = None
    sparse_score: float | None = None
    exact_score: float | None = None
    rrf_score: float | None = None
    rerank_score: float | None = None
    authority_level: int = Field(default=1, ge=0, le=10)
    quality_status: str | None = None
    is_authorized: bool
    can_support_medical_claim: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class UnifiedRetrievalResult(StrictModel):
    status: Literal["success", "no_result", "partial", "error", "forbidden", "timeout"]
    documents: list[UnifiedRetrievedEvidence] = Field(default_factory=list)
    error: RetrievalError | None = None
    warnings: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class ConstraintMatchResult(StrictModel):
    matched_numeric_constraints: list[str] = Field(default_factory=list)
    missing_numeric_constraints: list[str] = Field(default_factory=list)
    matched_population_constraints: list[str] = Field(default_factory=list)
    missing_population_constraints: list[str] = Field(default_factory=list)
    matched_time_constraints: list[str] = Field(default_factory=list)
    missing_time_constraints: list[str] = Field(default_factory=list)
    negation_consistent: bool = True
    score: float = Field(ge=0, le=1)


class SourceAuthority(StrictModel):
    source_type: str
    authority_level: int = Field(ge=0, le=10)
    evidence_type: str
    publication_date: date | None = None
    document_version: str | None = None
    region: str | None = None
    population: str | None = None


class EvidenceSufficiency(StrictModel):
    status: Literal["sufficient", "insufficient", "conflicting", "system_error"]
    confidence: float = Field(ge=0, le=1)
    matched_entities: list[str] = Field(default_factory=list)
    missing_entities: list[str] = Field(default_factory=list)
    matched_constraints: list[str] = Field(default_factory=list)
    missing_constraints: list[str] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    reason: str


class EvidenceConflict(StrictModel):
    topic: str
    evidence_ids: list[str]
    conflict_type: Literal["recommendation", "dosage", "population", "date", "definition"]
    summary: str
