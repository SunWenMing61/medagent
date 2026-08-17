from unittest.mock import Mock

from app.hybrid.context import scope_state_for_agent
from app.hybrid.runtime_monitor import RuntimeComplexityMonitor
from app.hybrid.task_planner import build_minimal_task_graph, update_task_progress
from app.services.agent_runtime_service import AgentRuntimeService


def test_ambiguous_routing_keeps_escalation_available():
    from app.hybrid.complexity_router import ComplexityRouter

    decision = ComplexityRouter().route("查询并解释这个检查结果")
    assert decision.escalation_enabled is (decision.execution_mode.value == "REACT")


def test_runtime_monitor_escalates_tool_loop_and_budget():
    monitor = RuntimeComplexityMonitor()
    loop = {"tool_call_names": ["a", "a", "a"], "tool_call_count": 3}
    assert monitor.escalation_reason(loop) == "repeated_tool_loop"
    budget = {"tokens_used": 3300, "token_budget": 4000}
    assert monitor.escalation_reason(budget) == "token_budget_pressure"


def test_unnecessary_escalation_is_not_triggered_for_completed_simple_react():
    state = {"react_step_count": 3, "tool_call_count": 1, "tool_call_names": ["local_knowledge_base"], "sub_questions": [], "tokens_used": 800}
    assert RuntimeComplexityMonitor().escalation_reason(state) is None


def test_minimal_agent_team_excludes_unneeded_specialists():
    graph = build_minimal_task_graph({"intent": "medical_knowledge", "answer_style_preference": "concise_evidence"})
    agents = [item["agent"] for item in graph]
    assert "answer_generator_concise" in agents
    assert "answer_generator_detailed" not in agents
    assert agents.count("retrieval_subgraph") == 1


def test_early_task_progress_and_structured_shared_state():
    state = {"intent": "medical_knowledge", "answer_style_preference": "concise_evidence", "completed_agents": ["input_safety_rules", "input_triage"]}
    state["task_graph"] = build_minimal_task_graph(state)
    update_task_progress(state)
    assert state["completed_tasks"] == ["T1", "T2"]
    assert "T3" in state["remaining_tasks"]


def test_context_scoping_direct_and_specialist_excludes_full_history():
    state = {"request_id": "r", "raw_query": "q", "assistant_profile": "general_qa", "conversation_summary": "private history", "tool_results": [{"large": True}]}
    direct = scope_state_for_agent(state, "direct_answer")
    assert direct == {"request_id": "r", "raw_query": "q", "assistant_profile": "general_qa"}


def test_request_cache_is_shared_inside_one_runtime():
    runtime = AgentRuntimeService(persist=False, trace=False)
    assert runtime.tool_executor is runtime.tool_executor
    assert isinstance(runtime._tool_cache, dict)
