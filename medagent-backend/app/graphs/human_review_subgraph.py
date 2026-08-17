"""Durable human-review interrupt subgraph."""

from langgraph.graph import END, START, StateGraph

from app.graphs.graph_state import AgentGraphState


def build_human_review_subgraph(runtime):
    def interrupt_for_review(state: AgentGraphState) -> dict:
        updated = dict(state)
        updated["human_review_required"] = True
        updated["status"] = "waiting_for_review"
        updated["current_agent"] = "human_review"
        updated.setdefault("completed_agents", []).append("human_review_interrupt")
        runtime.public_event(updated, "human_review_required", {"reason": updated.get("review_reason")})
        runtime.checkpoint(updated, "human_review")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("human_review_interrupt", interrupt_for_review)
    graph.add_edge(START, "human_review_interrupt")
    graph.add_edge("human_review_interrupt", END)
    return graph.compile()
