"""Application service for starting, resuming, reviewing and inspecting agent runs."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.graphs.graph_state import new_agent_state
from app.graphs.root_graph import build_controlled_workflow
from app.hybrid.runtime import HybridAgentRuntime
from app.models.agent_runtime import AgentRun, AgentStep, AgentToolCall, HumanReview
from app.services.checkpoint_service import checkpoint_service
from app.services.safety_service import RiskLevel, safety_service
from app.services.assistant_profile_service import assistant_profile_service


_CITATION = re.compile(r"\[(ev_[a-f0-9]{16})\]")


class AgentRunNotFound(LookupError):
    pass


class InvalidAgentRunTransition(ValueError):
    pass


class AgentRunService:
    def start(
        self,
        *,
        query: str,
        user_id: int,
        tenant_id: int,
        authorized_kb_ids: list[int],
        thread_id: str | None,
        conversation_summary: str,
        assistant_profile: str = "memory_qa",
        answer_style_preference: str = "concise_evidence",
    ) -> dict:
        profile = assistant_profile_service.get(assistant_profile)
        state = new_agent_state(
            raw_query=query,
            user_id=user_id,
            tenant_id=tenant_id,
            authorized_kb_ids=authorized_kb_ids,
            thread_id=thread_id,
            conversation_summary=conversation_summary,
            assistant_profile=profile.profile_id,
            persistent_memory_enabled=profile.session_memory_enabled,
            answer_style_preference=answer_style_preference,
        )
        return HybridAgentRuntime(persist=True, trace=True).run(state)

    def get(self, request_id: str, *, user_id: int, tenant_id: int) -> dict:
        state = checkpoint_service.load(request_id, user_id=user_id, tenant_id=tenant_id)
        if not state:
            raise AgentRunNotFound(request_id)
        return state

    def submit_clarification(
        self,
        request_id: str,
        response: str,
        *,
        user_id: int,
        tenant_id: int,
    ) -> dict:
        state = self.get(request_id, user_id=user_id, tenant_id=tenant_id)
        if state.get("status") != "waiting_for_user":
            raise InvalidAgentRunTransition("Run is not waiting for user clarification")
        combined = f"{state['raw_query']}\n用户补充：{response.strip()}"
        assessment = safety_service.assess(combined)
        state["raw_query"] = combined
        state["need_clarification"] = False
        state["clarification_questions"] = []
        state["status"] = "running"
        if assessment.level in {RiskLevel.EMERGENCY, RiskLevel.SELF_HARM}:
            state["risk_level"] = "emergency"
            state["need_emergency_response"] = True
            state["final_answer"] = safety_service.get_high_risk_response(assessment.matched, assessment.level)
            state["status"] = "completed"
            state["current_agent"] = "finalize"
            checkpoint_service.save(state, "finalize")
            return state
        # Triage already established the route; continue from query understanding.
        state["resume_node"] = "query_understanding"
        state["current_agent"] = "clarification"
        return build_controlled_workflow(persist=True, trace=True).run(state)

    def review(
        self,
        db: Session,
        request_id: str,
        *,
        reviewer_id: int,
        decision: str,
        edited_answer: str | None,
        comment: str | None,
    ) -> dict:
        run = db.query(AgentRun).filter(AgentRun.request_id == request_id).first()
        review = db.query(HumanReview).filter(HumanReview.request_id == request_id).first()
        if not run or not review:
            raise AgentRunNotFound(request_id)
        if run.status != "waiting_for_review" or review.status != "pending":
            raise InvalidAgentRunTransition("Run is not waiting for review")
        state = dict(run.state_json)
        review.reviewer_id = reviewer_id
        review.decision = decision
        review.comment = comment
        review.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if decision == "reject":
            review.status = "rejected"
            state["status"] = "rejected"
            state["final_answer"] = "该回答未通过人工审核，因此未向用户提供医学结论。"
            state["human_review_required"] = False
            state["current_agent"] = "human_review"
        elif decision == "edit":
            if not edited_answer:
                raise InvalidAgentRunTransition("edited_answer is required for an edit decision")
            unsafe = safety_service.check_output(edited_answer)
            if unsafe:
                raise InvalidAgentRunTransition("Edited answer still violates deterministic safety policy")
            allowed = {item["evidence_id"] for item in state.get("verified_evidence", [])}
            cited = set(_CITATION.findall(edited_answer))
            if not cited or not cited.issubset(allowed):
                raise InvalidAgentRunTransition("Edited answer must cite only verified evidence IDs")
            review.status = "edited"
            review.edited_answer = edited_answer
            state["status"] = "completed"
            state["final_answer"] = edited_answer
            state["safety_status"] = "pass"
            state["human_review_required"] = False
            state["current_agent"] = "finalize"
        else:
            if state.get("evidence_status") == "conflicting" and not state.get("answer_draft"):
                raise InvalidAgentRunTransition("Conflicting evidence requires an edited, citation-bound answer")
            review.status = "approved"
            state["safety_status"] = "pass"
            state["human_review_required"] = False
            state["status"] = "running"
            state["resume_node"] = "finalize"
            state["current_agent"] = "output_safety"

        run.state_json = state
        run.status = state["status"]
        run.final_answer = state.get("final_answer")
        db.commit()
        if decision == "approve":
            return build_controlled_workflow(persist=True, trace=True).run(state)
        checkpoint_service.save(state, state["current_agent"])
        return state

    @staticmethod
    def trace_summary(db: Session, request_id: str, *, user_id: int, tenant_id: int) -> dict:
        run = db.query(AgentRun).filter(
            AgentRun.request_id == request_id,
            AgentRun.user_id == user_id,
            AgentRun.tenant_id == tenant_id,
        ).first()
        if not run:
            raise AgentRunNotFound(request_id)
        steps = db.query(AgentStep).filter(AgentStep.request_id == request_id).order_by(AgentStep.id).all()
        tools = db.query(AgentToolCall).filter(AgentToolCall.request_id == request_id).order_by(AgentToolCall.id).all()
        return {
            "request_id": request_id,
            "execution_mode": (run.state_json or {}).get("execution_mode"),
            "initial_execution_mode": (run.state_json or {}).get("initial_execution_mode"),
            "complexity_level": (run.state_json or {}).get("complexity_level"),
            "router": (run.state_json or {}).get("router", {}),
            "escalated": bool((run.state_json or {}).get("escalated")),
            "escalation_reason": (run.state_json or {}).get("escalation_reason"),
            "steps": [{
                "agent_name": row.agent_name,
                "agent_version": row.agent_version,
                "prompt_version": row.prompt_version,
                "model": row.model,
                "status": row.status,
                "latency_ms": row.latency_ms,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "cost_usd": row.cost_usd,
                "error_code": row.error_code,
            } for row in steps],
            "tool_calls": [{
                "tool_name": row.tool_name,
                "arguments_hash": row.arguments_hash,
                "status": row.status,
                "latency_ms": row.latency_ms,
                "error_code": row.error_code,
                "result_count": row.result_count,
            } for row in tools],
        }


agent_run_service = AgentRunService()
