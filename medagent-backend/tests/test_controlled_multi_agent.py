"""Unit and integration coverage for the controlled Supervisor architecture."""

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.agents.evidence_verifier_agent import evidence_verifier_agent
from app.agents.input_triage_agent import input_triage_agent
from app.agents.schemas import EvidenceItem, RetrievalPlan, StructuredAnswer
from app.agents.supervisor import supervisor
from app.graphs.graph_state import new_agent_state
from app.graphs.root_graph import build_controlled_workflow
from app.services.agent_runtime_service import AgentRuntimeService
from app.tools.registry import tool_registry
from app.tools.schemas import LocalRetrievalInput, ToolContext, ToolExecutionResult


def _evidence(content: str = "高血压的一般管理应结合生活方式干预与专业评估。") -> dict:
    return EvidenceItem(
        evidence_id="ev_1234567890abcdef",
        content=content,
        source_type="local_knowledge_base",
        source_name="test-kb",
        document_id=10,
        chunk_id=20,
        page_num=3,
        retrieval_score=0.9,
        authority_level=7,
        is_authorized=True,
        is_conversation_memory=False,
    ).model_dump(mode="json")


class _FakeLocalTool:
    def __init__(self):
        self.calls = 0

    def execute(self, payload):
        self.calls += 1
        return ToolExecutionResult(status="ok", evidence=[_evidence()])


def test_agent_schema_rejects_unexpected_output_fields():
    with pytest.raises(ValidationError):
        StructuredAnswer.model_validate({"summary": "x", "unexpected": "unsafe"})


def test_rule_first_emergency_bypasses_all_agents_and_tools():
    state = new_agent_state(
        raw_query="突然胸痛并且呼吸困难", user_id=1, tenant_id=1, authorized_kb_ids=[2]
    )
    result = build_controlled_workflow(persist=False, trace=False).run(state)
    assert result["status"] == "completed"
    assert result["risk_level"] == "emergency"
    assert result["agent_call_count"] == 0
    assert result["tool_call_count"] == 0
    assert "紧急医疗" in result["final_answer"]


def test_vague_symptom_pauses_for_at_most_three_questions():
    state = new_agent_state(raw_query="我最近一直头痛", user_id=1, tenant_id=1, authorized_kb_ids=[])
    result = build_controlled_workflow(persist=False, trace=False).run(state)
    assert result["status"] == "waiting_for_user"
    assert 1 <= len(result["clarification_questions"]) <= 3
    assert result["tool_call_count"] == 0


def test_full_answer_uses_only_verified_evidence_and_backend_citations():
    fake = _FakeLocalTool()
    definition, original = tool_registry.get("local_knowledge_base")
    with patch.dict(tool_registry._items, {"local_knowledge_base": (definition, fake)}):
        state = new_agent_state(
            raw_query="高血压有哪些一般管理原则？",
            user_id=1,
            tenant_id=1,
            authorized_kb_ids=[5],
        )
        result = build_controlled_workflow(persist=False, trace=False).run(state)

    assert original is not fake
    assert result["status"] == "completed"
    assert result["evidence_status"] == "sufficient"
    assert result["safety_status"] == "pass"
    assert result["citations"][0]["evidence_id"] == "ev_1234567890abcdef"
    assert "[ev_1234567890abcdef]" in result["final_answer"]
    assert len(result["answer_variants"]) == 2
    assert {item["style"] for item in result["answer_variants"]} == {
        "concise_evidence", "detailed_guidance",
    }
    assert all(item["safety_status"] == "pass" for item in result["answer_variants"])
    assert result["answer_variants"][0]["evidence_basis_id"] == result["answer_variants"][1]["evidence_basis_id"]
    assert result["answer_variants"][0]["evidence_ids"] == result["answer_variants"][1]["evidence_ids"]


def test_learned_style_preference_changes_recommended_variant_order():
    fake = _FakeLocalTool()
    definition, _ = tool_registry.get("local_knowledge_base")
    with patch.dict(tool_registry._items, {"local_knowledge_base": (definition, fake)}):
        state = new_agent_state(
            raw_query="高血压有哪些一般管理原则？", user_id=1, tenant_id=1,
            authorized_kb_ids=[5], answer_style_preference="detailed_guidance",
        )
        result = build_controlled_workflow(persist=False, trace=False).run(state)
    assert result["recommended_variant_id"] == "variant_detailed"
    assert result["answer_variants"][0]["style"] == "detailed_guidance"


def test_insufficient_evidence_retries_only_once_then_refuses():
    result = build_controlled_workflow(persist=False, trace=False).run(
        new_agent_state(raw_query="解释一个医学概念", user_id=1, tenant_id=1, authorized_kb_ids=[])
    )
    assert result["retrieval_retry_count"] == 1
    assert result["evidence_status"] == "insufficient"
    assert "没有足够" in result["final_answer"]


def test_duplicate_tool_call_is_cached_and_not_counted_twice():
    fake = _FakeLocalTool()
    definition, _ = tool_registry.get("local_knowledge_base")
    runtime = AgentRuntimeService(persist=False, trace=False)
    state = new_agent_state(raw_query="q", user_id=1, tenant_id=1, authorized_kb_ids=[5])
    state["current_agent"] = "retrieval"
    payload = LocalRetrievalInput(
        context=ToolContext(request_id=state["request_id"], user_id=1, tenant_id=1, authorized_kb_ids=[5]),
        query="高血压",
    )
    with patch.dict(tool_registry._items, {"local_knowledge_base": (definition, fake)}):
        first = runtime.run_tool(state, "local_knowledge_base", payload)
        second = runtime.run_tool(state, "local_knowledge_base", payload)
    assert first.status == second.status
    assert first.evidence == second.evidence
    assert second.usage.cache_hit is True
    assert fake.calls == 1
    assert state["tool_call_count"] == 1
    assert any(event["type"] == "duplicate_tool_call" for event in state["public_events"])


def test_memory_and_unauthorized_items_can_never_support_medical_claims():
    plan = RetrievalPlan(
        original_query="阿司匹林作用",
        normalized_query="阿司匹林作用",
        local_queries=["阿司匹林作用"],
        retrieval_routes=["local_knowledge_base"],
        reason="test",
    )
    memory = _evidence("此前助手说阿司匹林适合所有人")
    memory.update({"evidence_id": "ev_memory00000001", "is_conversation_memory": True})
    denied = _evidence("未授权知识库内容")
    denied.update({"evidence_id": "ev_denied00000001", "is_authorized": False})
    result = evidence_verifier_agent.run(plan, [memory, denied])
    assert result.evidence_status == "insufficient"
    assert not result.supporting_evidence_ids
    assert set(result.rejected_evidence_ids) == {"ev_memory00000001", "ev_denied00000001"}


def test_supervisor_never_routes_around_output_safety():
    decision = supervisor.decide({"current_agent": "answer_generation", "status": "running"})
    assert decision.next_node == "output_safety"


def test_triage_detects_prescribing_boundary_as_high_risk():
    result = input_triage_agent.run("请给我开药并告诉我每天吃多少毫克")
    assert result.risk_level == "high"
    assert not result.need_emergency_response


def test_out_of_scope_query_stops_after_triage_without_retrieval():
    result = build_controlled_workflow(persist=False, trace=False).run(
        new_agent_state(raw_query="How do I sort a Python list?", user_id=1, tenant_id=1, authorized_kb_ids=[])
    )
    assert result["status"] == "completed"
    assert result["intent"] == "out_of_scope"
    assert result["agent_call_count"] == 1
    assert result["tool_call_count"] == 0
    assert "不属于医疗健康问答范围" in result["final_answer"]


def test_general_profile_routes_non_medical_query_directly_to_the_model():
    result = input_triage_agent.run("How do I sort a Python list?", "general_qa")
    assert result.intent == "general_knowledge"
    assert result.required_routes == []


def test_general_profile_keeps_medical_questions_on_grounded_hybrid_retrieval():
    result = input_triage_agent.run("高血压的一般管理原则是什么？", "general_qa")
    assert result.intent == "medical_knowledge"
    assert result.required_routes == ["local_rag", "online_web"]


def test_memory_profile_keeps_non_medical_query_out_of_scope():
    result = input_triage_agent.run("How do I sort a Python list?", "memory_qa")
    assert result.intent == "out_of_scope"
    assert result.required_routes == []
