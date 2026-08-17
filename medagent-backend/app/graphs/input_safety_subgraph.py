"""Rule-first input safety subgraph."""

from langgraph.graph import END, START, StateGraph

from app.graphs.graph_state import AgentGraphState
from app.services.safety_service import RiskLevel, safety_service


def build_input_safety_subgraph(runtime):
    def rule_prescreen(state: AgentGraphState) -> dict:
        updated = dict(state)
        assessment = safety_service.assess(updated["raw_query"])
        if assessment.level in {RiskLevel.EMERGENCY, RiskLevel.SELF_HARM}:
            updated["risk_level"] = "emergency"
            updated["emergency_flags"] = assessment.matched
            updated["need_emergency_response"] = True
            updated["final_answer"] = safety_service.get_high_risk_response(assessment.matched, assessment.level)
        updated["current_agent"] = "input_safety"
        updated.setdefault("completed_agents", []).append("input_safety_rules")
        runtime.public_event(updated, "input_safety", {"risk_level": updated.get("risk_level", "low")})
        runtime.checkpoint(updated, "input_safety")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("rule_prescreen", rule_prescreen)
    graph.add_edge(START, "rule_prescreen")
    graph.add_edge("rule_prescreen", END)
    return graph.compile()
