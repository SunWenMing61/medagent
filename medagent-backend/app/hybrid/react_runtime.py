"""Single-orchestrator ReAct path with bounded dynamic escalation."""

from __future__ import annotations

from app.graphs.answer_subgraph import build_answer_subgraph
from app.graphs.evidence_subgraph import build_evidence_subgraph
from app.graphs.input_safety_subgraph import build_input_safety_subgraph
from app.graphs.output_safety_subgraph import build_output_safety_subgraph
from app.graphs.query_understanding_subgraph import build_query_understanding_subgraph
from app.graphs.retrieval_subgraph import build_retrieval_subgraph
from app.graphs.root_graph import ControlledMedAgentWorkflow
from app.graphs.triage_subgraph import build_clarification_subgraph, build_triage_subgraph
from app.hybrid.contracts import EscalationRequired
from app.hybrid.runtime_monitor import runtime_complexity_monitor


class ReActRuntime:
    """Execute an explicit observe/act sequence without a supervisor loop."""

    def __init__(self, runtime) -> None:
        self.runtime = runtime

    def _step(self, state: dict, name: str, graph) -> dict:
        updated = dict(graph.invoke(state))
        updated["react_step_count"] = int(updated.get("react_step_count", 0)) + 1
        snapshot = runtime_complexity_monitor.snapshot(updated)
        updated["runtime_monitor"] = snapshot.as_dict()
        self.runtime.public_event(updated, "react_step", {
            "action": name,
            "decision_summary": f"completed {name}",
            "runtime_complexity": snapshot.as_dict(),
        })
        return updated

    @staticmethod
    def _escalation_reason(state: dict) -> str | None:
        return runtime_complexity_monitor.escalation_reason(state)

    def run(self, state: dict, *, escalation_enabled: bool) -> dict:
        updated = dict(state)
        updated = self._step(updated, "input_safety", build_input_safety_subgraph(self.runtime))
        if not updated.get("need_emergency_response"):
            updated = self._step(updated, "triage", build_triage_subgraph(self.runtime))
        if updated.get("need_clarification"):
            return self._step(updated, "clarification", build_clarification_subgraph(self.runtime))
        if not updated.get("need_emergency_response") and updated.get("intent") != "out_of_scope":
            updated = self._step(updated, "query_understanding", build_query_understanding_subgraph(self.runtime))
            reason = self._escalation_reason(updated)
            if escalation_enabled and reason:
                updated["resume_node"] = "retrieval"
                raise EscalationRequired(reason, updated)
            updated = self._step(updated, "retrieval", build_retrieval_subgraph(self.runtime))
            updated = self._step(updated, "evidence_verification", build_evidence_subgraph(self.runtime))
            reason = self._escalation_reason(updated)
            if escalation_enabled and reason:
                updated["resume_node"] = "answer_generation" if updated.get("evidence_status") != "conflicting" else "retrieval"
                raise EscalationRequired(reason, updated)
            updated = self._step(updated, "answer_generation", build_answer_subgraph(self.runtime))
            updated = self._step(updated, "output_safety", build_output_safety_subgraph(self.runtime))
        return ControlledMedAgentWorkflow(self.runtime)._finalize_node(updated)
