"""Minimal direct-answer path for simple, no-tool, no-RAG requests."""

from __future__ import annotations

from app.graphs.input_safety_subgraph import build_input_safety_subgraph
from app.graphs.output_safety_subgraph import build_output_safety_subgraph
from app.graphs.root_graph import ControlledMedAgentWorkflow
from app.graphs.triage_subgraph import build_triage_subgraph
from app.hybrid.context import scope_state_for_agent
from app.agents.answer_generator_agent import answer_generator_concise_agent


class DirectRuntime:
    """One answer call with deterministic safety before and after generation."""

    def __init__(self, runtime) -> None:
        self.runtime = runtime

    def run(self, state: dict) -> dict:
        updated = dict(build_input_safety_subgraph(self.runtime).invoke(dict(state)))
        if updated.get("need_emergency_response"):
            return ControlledMedAgentWorkflow(self.runtime)._finalize_node(updated)
        updated = dict(build_triage_subgraph(self.runtime).invoke(updated))
        if updated.get("need_clarification") or updated.get("intent") == "out_of_scope":
            return ControlledMedAgentWorkflow(self.runtime)._finalize_node(updated)
        context = scope_state_for_agent(updated, "direct_answer")
        answer = self.runtime.run_agent(
            updated,
            "answer_generator_concise",
            answer_generator_concise_agent.run,
            context["raw_query"],
            [],
            general_mode=True,
        )
        draft = answer.model_dump(mode="json")
        updated["answer_draft"] = draft
        updated["answer_candidates"] = [{
            "variant_id": "variant_direct",
            "style": "concise_evidence",
            "label": "直接回答",
            "agent_name": "answer_generator_concise",
            "request_id": updated["request_id"],
            "answer_draft": draft,
            "citations": [],
            "evidence_basis_id": "direct_no_retrieval",
            "evidence_ids": [],
            "evidence_count": 0,
            "safety_status": "pending",
        }]
        updated["evidence_status"] = "not_required"
        updated["current_agent"] = "answer_generation"
        updated.setdefault("completed_agents", []).append("answer_generator_concise")
        self.runtime.public_event(updated, "direct_answer", {"decision_summary": "single direct model call; no RAG or tool"})
        updated = dict(build_output_safety_subgraph(self.runtime).invoke(updated))
        return ControlledMedAgentWorkflow(self.runtime)._finalize_node(updated)
