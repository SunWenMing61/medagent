"""Public API contracts for controlled agent runs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=8000)
    kb_ids: list[int] | None = None
    thread_id: str | None = Field(default=None, max_length=64)
    conversation_summary: str = Field(default="", max_length=4000)
    assistant_profile: Literal["general_qa", "memory_qa"] = "memory_qa"


class AgentRunResponse(BaseModel):
    request_id: str
    thread_id: str
    status: str
    current_node: str
    intent: str
    risk_level: str
    evidence_status: str
    safety_status: str
    human_review_required: bool
    clarification_questions: list[str]
    answer: str
    citations: list[dict]
    errors: list[dict]
    agent_call_count: int
    tool_call_count: int
    answer_variants: list[dict] = Field(default_factory=list)
    recommended_variant_id: str | None = None


class ClarificationSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response: str = Field(min_length=1, max_length=4000)


class HumanReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "edit", "reject"]
    edited_answer: str | None = Field(default=None, max_length=12000)
    comment: str | None = Field(default=None, max_length=4000)


class AgentTraceResponse(BaseModel):
    request_id: str
    steps: list[dict]
    tool_calls: list[dict]
