"""The only component allowed to choose the next graph node."""

from __future__ import annotations

from app.agents.schemas import SupervisorDecision


class Supervisor:
    name = "supervisor"
    version = "1.0.0"

    def decide(self, state: dict, *, human_review_enabled: bool = True) -> SupervisorDecision:
        if state.get("status") in {"completed", "failed", "cancelled", "waiting_for_user", "waiting_for_review"}:
            return SupervisorDecision(next_node="end", reason="Workflow is in a terminal or interrupt state.")

        current = state.get("current_agent", "input_safety")
        if current == "input_safety":
            target = "finalize" if state.get("need_emergency_response") else "triage"
        elif current == "triage":
            if state.get("intent") == "out_of_scope":
                target = "finalize"
            elif state.get("intent") == "general_knowledge":
                target = "answer_generation"
            else:
                target = "clarification" if state.get("need_clarification") else "query_understanding"
        elif current == "clarification":
            target = "end"
        elif current == "query_understanding":
            target = "retrieval"
        elif current == "retrieval":
            target = "evidence_verification"
        elif current == "evidence_verification":
            evidence_status = state.get("evidence_status")
            if evidence_status == "sufficient":
                target = "answer_generation"
            elif evidence_status == "insufficient" and int(state.get("retrieval_retry_count", 0)) < 1:
                target = "retrieval"
            elif evidence_status == "conflicting" and human_review_enabled:
                target = "human_review"
            else:
                target = "finalize"
        elif current == "answer_generation":
            target = "output_safety"
        elif current == "output_safety":
            safety = state.get("safety_status")
            if safety == "pass":
                target = "finalize"
            elif safety == "rewrite_required" and int(state.get("safety_rewrite_count", 0)) < 1:
                target = "answer_generation"
            elif human_review_enabled and safety in {"human_review_required", "blocked"}:
                target = "human_review"
            else:
                target = "finalize"
        elif current == "human_review":
            target = "end"
        elif current == "finalize":
            target = "end"
        else:
            target = "finalize"
        return SupervisorDecision(next_node=target, reason=f"Controlled transition after {current}.")


supervisor = Supervisor()
