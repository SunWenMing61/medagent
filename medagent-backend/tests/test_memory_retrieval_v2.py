"""Security and quality regressions for layered Memory and Retrieval v2."""

import time

from app.agents.evidence_verifier_agent import EvidenceVerifierAgent
from app.agents.schemas import RetrievalPlan
from app.schemas.memory import MemoryCandidate
from app.services.memory_service import MemoryPolicyService, memory_namespace
from app.services.retrieval_service import HybridRetriever, RetrievalStatus, reciprocal_rank_fusion


def _candidate(**overrides):
    values = dict(
        memory_type="semantic", category="preference", subject="user", predicate="language",
        value="Chinese", confidence=1.0, importance=0.8, reason_to_remember="explicit",
        sensitivity="normal", source_type="user_explicit", source_role="user",
        explicit_instruction=True, confirmed=True,
    )
    values.update(overrides)
    return MemoryCandidate(**values)


def test_namespace_is_tenant_user_and_type_scoped():
    assert memory_namespace(8, 12, "semantic") != memory_namespace(8, 13, "semantic")
    assert memory_namespace(8, 12, "semantic") != memory_namespace(9, 12, "semantic")


def test_assistant_and_external_facts_never_enter_long_term_memory():
    policy = MemoryPolicyService()
    assistant = policy.decide_write(
        _candidate(source_role="assistant", source_type="model_inferred"),
        agent_name="user_control", long_term_enabled=True,
    )
    external = policy.decide_write(
        _candidate(source_type="external_retrieval"),
        agent_name="user_control", long_term_enabled=True,
    )
    assert not assistant.allowed
    assert not external.allowed


def test_medical_sensitive_memory_requires_system_and_user_opt_in():
    decision = MemoryPolicyService().decide_write(
        _candidate(sensitivity="medical_sensitive"), agent_name="user_control",
        long_term_enabled=True, medical_sensitive_enabled=False,
    )
    assert not decision.allowed


def test_memory_cannot_support_medical_claim_and_dosage_conflict_is_detected():
    plan = RetrievalPlan(original_query="阿司匹林剂量", normalized_query="阿司匹林剂量", reason="test")
    result = EvidenceVerifierAgent().run(plan, [
        {"evidence_id": "memory", "content": "阿司匹林 50 mg", "source_type": "conversation_memory", "source_name": "memory", "is_authorized": True, "is_conversation_memory": True, "can_support_medical_claim": False},
        {"evidence_id": "e1", "content": "推荐阿司匹林 50 mg 每日一次", "source_type": "clinical_guideline", "source_name": "g1", "is_authorized": True, "is_conversation_memory": False},
        {"evidence_id": "e2", "content": "推荐阿司匹林 100 mg 每日一次", "source_type": "drug_label", "source_name": "d1", "is_authorized": True, "is_conversation_memory": False},
    ])
    assert "memory" in result.rejected_evidence_ids
    assert result.evidence_status == "conflicting"
    assert set(result.conflicting_evidence_ids) == {"e1", "e2"}


def test_rrf_preserves_exact_route_and_timeout_returns_without_waiting(monkeypatch):
    fused = reciprocal_rank_fusion([
        [{"id": 1, "document_id": 1, "content": "a", "exact_score": 1.0}],
        [{"id": 2, "document_id": 1, "content": "b"}, {"id": 1, "document_id": 1, "content": "a"}],
    ])
    assert fused[0]["id"] == 1
    monkeypatch.setattr("app.services.retrieval_service.settings.RETRIEVAL_TIMEOUT_SECONDS", 0.02)

    def slow(*_):
        time.sleep(0.25)
        return []

    started = time.perf_counter()
    result = HybridRetriever(slow, slow).retrieve("query", [1])
    elapsed = time.perf_counter() - started
    assert result.status == RetrievalStatus.TIMEOUT
    assert elapsed < 0.15
