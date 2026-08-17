"""Verified-evidence-only answer generation subgraph."""

import hashlib
import json

from langgraph.graph import END, START, StateGraph

from app.agents.answer_generator_agent import (
    answer_generator_concise_agent,
    answer_generator_detailed_agent,
)
from app.graphs.graph_state import AgentGraphState
from app.services.evidence_service import bind_public_citations


def build_answer_subgraph(runtime):
    def answer_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        rewrite = int(updated.get("safety_rewrite_count", 0)) > 0
        # Both agents must receive the exact same, ordered evidence basis. They
        # may differ only in presentation style, never in supporting sources.
        answer_evidence = list(updated.get("verified_evidence", []))[:4]
        general_mode = bool(
            updated.get("assistant_profile") == "general_qa"
            and updated.get("intent") == "general_knowledge"
        )
        basis_material = [{
            "evidence_id": item.get("evidence_id"),
            "content_sha256": hashlib.sha256(str(item.get("content", "")).encode("utf-8")).hexdigest(),
        } for item in answer_evidence]
        evidence_basis_id = "basis_" + hashlib.sha256(
            json.dumps(basis_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:20]
        common_basis_citations, common_basis_ids = bind_public_citations(
            {"details": [{"citation_ids": [item["evidence_id"]]} for item in answer_evidence]},
            answer_evidence,
        )
        candidates = []
        for variant_id, style, label, agent in (
            ("variant_concise", "concise_evidence", "精炼证据版", answer_generator_concise_agent),
            ("variant_detailed", "detailed_guidance", "详细指导版", answer_generator_detailed_agent),
        ):
            result = runtime.run_agent(
                updated,
                agent.name,
                agent.run,
                updated["raw_query"],
                answer_evidence,
                rewrite=rewrite,
                general_mode=general_mode,
            )
            answer = result.model_dump(mode="json")
            # Validate every claim citation, then expose the exact same complete
            # evidence basis for both answer styles. This prevents two model
            # calls from silently presenting different sources to the user.
            bind_public_citations(answer, answer_evidence)
            candidates.append({
                "variant_id": variant_id,
                "style": style,
                "label": label,
                "agent_name": agent.name,
                "request_id": updated["request_id"],
                "answer_draft": answer,
                "citations": common_basis_citations,
                "evidence_basis_id": evidence_basis_id,
                "evidence_ids": common_basis_ids,
                "evidence_count": len(common_basis_ids),
                "safety_status": "pending",
            })
        citation_bases = [tuple(item["evidence_ids"]) for item in candidates]
        if len(set(citation_bases)) != 1:
            raise ValueError("Dual answer agents produced different evidence bases")
        preference = updated.get("answer_style_preference", "concise_evidence")
        candidates.sort(key=lambda item: (item["style"] != preference, item["variant_id"]))
        primary = candidates[0]
        updated["answer_candidates"] = candidates
        updated["answer_draft"] = primary["answer_draft"]
        updated["structured_claims"] = primary["answer_draft"]["details"]
        updated["citations"] = primary["citations"]
        updated["current_agent"] = "answer_generation"
        updated.setdefault("completed_agents", []).extend([item["agent_name"] for item in candidates])
        runtime.public_event(updated, "answer_candidates_generated", {
            "variant_count": len(candidates),
            "styles": [item["style"] for item in candidates],
            "preferred_style": preference,
            "evidence_basis_id": evidence_basis_id,
            "evidence_count": candidates[0]["evidence_count"],
        })
        runtime.checkpoint(updated, "answer_generation")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("answer_generator_agent", answer_node)
    graph.add_edge(START, "answer_generator_agent")
    graph.add_edge("answer_generator_agent", END)
    return graph.compile()
