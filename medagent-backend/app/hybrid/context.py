"""Least-context projections used when specialists collaborate."""

from __future__ import annotations


COMMON = {"request_id", "thread_id", "user_id", "tenant_id", "intent", "risk_level", "token_budget", "tokens_used"}
SCOPES = {
    "direct_answer": COMMON | {"raw_query", "assistant_profile"},
    "query_understanding": COMMON | {"raw_query", "conversation_summary", "triage_result", "active_topic", "active_entities", "confirmed_constraints"},
    "retrieval": COMMON | {"standalone_query", "normalized_query", "sub_questions", "retrieval_plan", "authorized_kb_ids", "permission_tags"},
    "evidence_verification": COMMON | {"candidate_evidence", "retrieved_evidence", "retrieval_issues"},
    "answer_generation": COMMON | {"standalone_query", "verified_evidence", "evidence_status", "answer_style_preference"},
    "output_safety": COMMON | {"answer_draft", "answer_candidates", "citations", "evidence_status"},
}


def scope_state_for_agent(state: dict, agent_name: str) -> dict:
    """Return a structured projection, excluding raw history and unrelated tool output."""
    allowed = SCOPES.get(agent_name, COMMON)
    return {key: state[key] for key in allowed if key in state}
