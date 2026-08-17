"""Serializable state for the controlled-agent workflow."""

from datetime import datetime, timezone
from typing import TypedDict
from uuid import uuid4


class AgentGraphState(TypedDict, total=False):
    """State shared by the supervisor and its bounded subgraphs."""

    state_version: str
    request_id: str
    thread_id: str
    user_id: int
    tenant_id: int
    raw_query: str
    initial_execution_mode: str
    execution_mode: str
    complexity_level: str
    router: dict
    escalated: bool
    escalation_reason: str | None
    hybrid_latency_ms: float
    request_context: dict
    memory_architecture_version: str
    assistant_profile: str
    persistent_memory_enabled: bool
    conversation_summary: str
    active_topic: str | None
    active_entities: list[dict]
    unresolved_questions: list[dict]
    confirmed_constraints: list[dict]
    authorized_kb_ids: list[int]
    permission_tags: list[str]
    intent: str
    risk_level: str
    emergency_flags: list[str]
    need_emergency_response: bool
    need_clarification: bool
    clarification_questions: list[str]
    normalized_query: str
    standalone_query: str
    medical_entities: list[dict]
    numeric_constraints: list[dict]
    population_constraints: list[str]
    time_constraints: list[str]
    negations: list[str]
    sub_questions: list[dict]
    retrieval_plan: dict
    triage_result: dict
    local_evidence: list[dict]
    online_evidence: list[dict]
    candidate_evidence: list[dict]
    retrieval_issues: list[dict]
    retrieved_evidence: list[dict]
    retrieval_results: list[dict]
    tool_results: list[dict]
    facts: dict
    final_evidence: list[dict]
    memory_context: list[dict]
    episodic_context: list[dict]
    procedural_context: list[dict]
    verified_evidence: list[dict]
    rejected_evidence: list[dict]
    evidence_status: str
    evidence_conflicts: list[dict]
    answer_draft: dict | None
    answer_style_preference: str
    answer_candidates: list[dict]
    answer_variants: list[dict]
    recommended_variant_id: str | None
    structured_claims: list[dict]
    citations: list[dict]
    final_answer: str
    safety_flags: list[str]
    safety_status: str
    human_review_required: bool
    review_reason: str
    current_agent: str
    next_node: str
    resume_node: str
    completed_agents: list[str]
    selected_agents: list[str]
    task_graph: list[dict]
    completed_tasks: list[str]
    remaining_tasks: list[str]
    early_terminated: bool
    agent_call_count: int
    tool_call_count: int
    retrieval_retry_count: int
    query_rewrite_count: int
    safety_rewrite_count: int
    token_budget: int
    tokens_used: int
    tool_call_hashes: list[str]
    tool_call_names: list[str]
    tool_failure_count: int
    react_step_count: int
    runtime_monitor: dict
    errors: list[dict]
    public_events: list[dict]
    retrieval_trace: dict
    status: str
    created_at: str
    updated_at: str


def new_agent_state(
    *,
    raw_query: str,
    user_id: int,
    tenant_id: int,
    authorized_kb_ids: list[int],
    thread_id: str | None = None,
    request_id: str | None = None,
    conversation_summary: str = "",
    token_budget: int = 6000,
    assistant_profile: str = "memory_qa",
    persistent_memory_enabled: bool = True,
    answer_style_preference: str = "concise_evidence",
) -> AgentGraphState:
    """Create a complete, versioned state with safe defaults."""

    from app.core.config import settings
    from app.schemas.memory import RequestContext

    now = datetime.now(timezone.utc).isoformat()
    request_key = request_id or f"req_{uuid4().hex}"
    thread_key = thread_id or f"thread_{uuid4().hex}"
    normalized_kbs = sorted({int(item) for item in authorized_kb_ids})
    scopes = ["memory:read"] + (["kb:read"] if normalized_kbs else [])
    request_context = RequestContext(
        request_id=request_key,
        thread_id=thread_key,
        user_id=int(user_id),
        tenant_id=int(tenant_id),
        raw_query=raw_query.strip(),
        authorized_kb_ids=normalized_kbs,
        permission_scopes=scopes,
        token_budget=max(int(token_budget), 256),
        tool_call_budget=settings.TOOL_MAX_CALLS,
    )
    return AgentGraphState(
        state_version="ma-v1",
        memory_architecture_version="memory-retrieval-v2",
        assistant_profile=assistant_profile,
        persistent_memory_enabled=bool(persistent_memory_enabled),
        request_id=request_key,
        thread_id=thread_key,
        user_id=int(user_id),
        tenant_id=int(tenant_id),
        raw_query=raw_query.strip(),
        initial_execution_mode="",
        execution_mode="",
        complexity_level="",
        router={},
        escalated=False,
        escalation_reason=None,
        hybrid_latency_ms=0.0,
        request_context=request_context.model_dump(mode="json"),
        conversation_summary=conversation_summary,
        active_topic=None,
        active_entities=[],
        unresolved_questions=[],
        confirmed_constraints=[],
        authorized_kb_ids=normalized_kbs,
        permission_tags=[],
        intent="unknown",
        risk_level="low",
        emergency_flags=[],
        need_emergency_response=False,
        need_clarification=False,
        clarification_questions=[],
        normalized_query="",
        standalone_query="",
        medical_entities=[],
        numeric_constraints=[],
        population_constraints=[],
        time_constraints=[],
        negations=[],
        sub_questions=[],
        retrieval_plan={},
        triage_result={},
        local_evidence=[],
        online_evidence=[],
        candidate_evidence=[],
        retrieval_issues=[],
        retrieved_evidence=[],
        retrieval_results=[],
        tool_results=[],
        facts={},
        final_evidence=[],
        memory_context=[],
        episodic_context=[],
        procedural_context=[],
        verified_evidence=[],
        rejected_evidence=[],
        evidence_status="not_run",
        evidence_conflicts=[],
        answer_draft=None,
        answer_style_preference=answer_style_preference,
        answer_candidates=[],
        answer_variants=[],
        recommended_variant_id=None,
        structured_claims=[],
        citations=[],
        final_answer="",
        safety_flags=[],
        safety_status="not_run",
        human_review_required=False,
        review_reason="",
        current_agent="input_safety",
        next_node="input_safety",
        resume_node="input_safety",
        completed_agents=[],
        selected_agents=[],
        task_graph=[],
        completed_tasks=[],
        remaining_tasks=[],
        early_terminated=False,
        agent_call_count=0,
        tool_call_count=0,
        retrieval_retry_count=0,
        query_rewrite_count=0,
        safety_rewrite_count=0,
        token_budget=max(int(token_budget), 256),
        tokens_used=0,
        tool_call_hashes=[],
        tool_call_names=[],
        tool_failure_count=0,
        react_step_count=0,
        runtime_monitor={},
        errors=[],
        public_events=[],
        retrieval_trace={},
        status="running",
        created_at=now,
        updated_at=now,
    )
