"""Evidence verification subgraph."""

from langgraph.graph import END, START, StateGraph

from app.agents.evidence_verifier_agent import evidence_verifier_agent
from app.agents.schemas import RetrievalPlan
from app.graphs.graph_state import AgentGraphState


def build_evidence_subgraph(runtime):
    def verify_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        plan = RetrievalPlan.model_validate(updated["retrieval_plan"])
        local_error = any(item.get("component") == "local" for item in updated.get("retrieval_issues", []))
        result = runtime.run_agent(
            updated,
            "evidence_verifier",
            evidence_verifier_agent.run,
            plan,
            updated.get("retrieved_evidence", []),
            retrieval_had_system_error=local_error,
        )
        support = set(result.supporting_evidence_ids)
        rejected = set(result.rejected_evidence_ids)
        updated["verified_evidence"] = [
            item for item in updated.get("retrieved_evidence", []) if item.get("evidence_id") in support
        ]
        updated["rejected_evidence"] = [
            item for item in updated.get("retrieved_evidence", []) if item.get("evidence_id") in rejected
        ]
        updated["evidence_status"] = result.evidence_status
        updated["evidence_conflicts"] = [
            {"evidence_id": item} for item in result.conflicting_evidence_ids
        ]
        updated["current_agent"] = "evidence_verification"
        updated.setdefault("completed_agents", []).append("evidence_verifier")
        runtime.public_event(updated, "evidence_verification", {
            "status": result.evidence_status,
            "supporting_count": len(result.supporting_evidence_ids),
            "recommended_action": result.recommended_action,
        })
        runtime.checkpoint(updated, "evidence_verification")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("evidence_verifier_agent", verify_node)
    graph.add_edge(START, "evidence_verifier_agent")
    graph.add_edge("evidence_verifier_agent", END)
    return graph.compile()
