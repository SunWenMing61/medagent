"""Conclusion/citation consistency and output safety subgraph."""

from langgraph.graph import END, START, StateGraph

from app.agents.output_safety_agent import output_safety_agent
from app.agents.schemas import StructuredAnswer
from app.graphs.graph_state import AgentGraphState


def build_output_safety_subgraph(runtime):
    def safety_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        try:
            allowed = {item["evidence_id"] for item in updated.get("verified_evidence", [])}
            candidates = updated.get("answer_candidates") or [{
                "variant_id": "variant_concise",
                "style": "concise_evidence",
                "label": "精炼证据版",
                "agent_name": "answer_generator_concise",
                "request_id": updated["request_id"],
                "answer_draft": updated["answer_draft"],
                "citations": updated.get("citations", []),
            }]
            statuses = []
            reasons = []
            flags = []
            reviewed = []
            for candidate in candidates:
                answer = StructuredAnswer.model_validate(candidate["answer_draft"])
                result = runtime.run_agent(
                    updated,
                    "output_safety",
                    output_safety_agent.run,
                    answer,
                    allowed_evidence_ids=allowed,
                    risk_level=updated.get("risk_level", "low"),
                )
                candidate = dict(candidate)
                candidate["safety_status"] = result.safety_status
                candidate["safety_flags"] = result.risk_categories
                candidate["safety_reason"] = result.reason
                reviewed.append(candidate)
                statuses.append(result.safety_status)
                reasons.append(result.reason)
                flags.extend(result.risk_categories)
            updated["answer_candidates"] = reviewed
            if all(status == "pass" for status in statuses):
                overall = "pass"
            elif "human_review_required" in statuses:
                overall = "human_review_required"
            elif "rewrite_required" in statuses:
                overall = "rewrite_required"
            else:
                overall = "blocked"
            updated["safety_status"] = overall
            updated["safety_flags"] = list(dict.fromkeys(flags))
            updated["human_review_required"] = overall == "human_review_required"
            updated["review_reason"] = "; ".join(reasons) if updated["human_review_required"] else ""
        except Exception as exc:
            runtime.add_error(updated, "output_safety", "SAFETY_AGENT_FAILURE", str(exc), False)
            updated["safety_status"] = "blocked"
            updated["safety_flags"] = ["safety_agent_failure"]
            updated["human_review_required"] = updated.get("risk_level") in {"medium", "high", "emergency"}
            updated["review_reason"] = "Safety review failed closed."
        updated["current_agent"] = "output_safety"
        updated.setdefault("completed_agents", []).append("output_safety")
        runtime.public_event(updated, "safety_review", {
            "status": updated["safety_status"],
            "human_review_required": updated["human_review_required"],
        })
        runtime.checkpoint(updated, "output_safety")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("output_safety_agent", safety_node)
    graph.add_edge(START, "output_safety_agent")
    graph.add_edge("output_safety_agent", END)
    return graph.compile()
