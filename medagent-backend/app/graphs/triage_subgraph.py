"""Input triage and clarification subgraphs."""

from langgraph.graph import END, START, StateGraph

from app.agents.clarification_agent import clarification_agent
from app.agents.input_triage_agent import input_triage_agent
from app.agents.schemas import InputTriageResult
from app.graphs.graph_state import AgentGraphState


def build_triage_subgraph(runtime):
    def triage_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        result = runtime.run_agent(
            updated,
            "input_triage",
            input_triage_agent.run,
            updated["raw_query"],
            updated.get("assistant_profile", "memory_qa"),
        )
        updated["triage_result"] = result.model_dump(mode="json")
        updated["intent"] = result.intent
        updated["risk_level"] = result.risk_level
        updated["need_emergency_response"] = result.need_emergency_response
        updated["need_clarification"] = result.need_clarification
        updated["medical_entities"] = result.medical_entities
        updated["current_agent"] = "triage"
        updated.setdefault("completed_agents", []).append("input_triage")
        runtime.public_event(updated, "triage", {
            "intent": result.intent, "risk_level": result.risk_level,
            "need_clarification": result.need_clarification,
        })
        runtime.checkpoint(updated, "triage")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("input_triage_agent", triage_node)
    graph.add_edge(START, "input_triage_agent")
    graph.add_edge("input_triage_agent", END)
    return graph.compile()


def build_clarification_subgraph(runtime):
    def clarification_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        triage = InputTriageResult.model_validate(updated["triage_result"])
        result = runtime.run_agent(updated, "medical_clarification", clarification_agent.run, triage)
        updated["clarification_questions"] = result.questions
        updated["need_clarification"] = result.need_clarification
        updated["current_agent"] = "clarification"
        updated["status"] = "waiting_for_user" if result.need_clarification else "running"
        if result.need_clarification:
            updated["final_answer"] = "为了更安全地回答，请先补充：\n" + "\n".join(
                f"{index}. {question}" for index, question in enumerate(result.questions, start=1)
            )
        updated.setdefault("completed_agents", []).append("medical_clarification")
        runtime.public_event(updated, "clarification_required", {"questions": result.questions})
        runtime.checkpoint(updated, "clarification")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("medical_clarification_agent", clarification_node)
    graph.add_edge(START, "medical_clarification_agent")
    graph.add_edge("medical_clarification_agent", END)
    return graph.compile()
