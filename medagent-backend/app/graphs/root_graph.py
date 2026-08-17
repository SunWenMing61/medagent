"""Single-Supervisor controlled multi-agent LangGraph."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.supervisor import supervisor
from app.core.config import settings
from app.graphs.answer_subgraph import build_answer_subgraph
from app.graphs.evidence_subgraph import build_evidence_subgraph
from app.graphs.graph_state import AgentGraphState
from app.graphs.human_review_subgraph import build_human_review_subgraph
from app.graphs.input_safety_subgraph import build_input_safety_subgraph
from app.graphs.output_safety_subgraph import build_output_safety_subgraph
from app.graphs.query_understanding_subgraph import build_query_understanding_subgraph
from app.graphs.retrieval_subgraph import build_retrieval_subgraph
from app.graphs.triage_subgraph import build_clarification_subgraph, build_triage_subgraph
from app.services.agent_runtime_service import AgentLimitExceeded, AgentRuntimeService, ToolLimitExceeded
from app.services.safety_service import safety_service
from app.hybrid.task_planner import build_minimal_task_graph, update_task_progress


def _render_structured_answer(answer: dict) -> str:
    lines = [answer.get("summary", "")]
    for detail in answer.get("details", []):
        citations = " ".join(f"[{item}]" for item in detail.get("citation_ids", []))
        lines.append(f"- {detail.get('claim', '')} {citations}".strip())
    if answer.get("uncertainty"):
        lines.append(f"不确定性：{answer['uncertainty']}")
    for limitation in answer.get("limitations", []):
        lines.append(f"限制：{limitation}")
    if answer.get("recommended_next_step"):
        lines.append(answer["recommended_next_step"])
    if answer.get("needs_professional_consultation"):
        lines.append(safety_service.get_disclaimer())
    return "\n\n".join(item for item in lines if item)


def _render_verified_answer(state: dict) -> str:
    return _render_structured_answer(state.get("answer_draft") or {})


class ControlledMedAgentWorkflow:
    """Build and execute a bounded graph; specialist agents never select peers."""

    def __init__(self, runtime: AgentRuntimeService | None = None) -> None:
        self.runtime = runtime or AgentRuntimeService()
        self.graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentGraphState)
        graph.add_node("input_safety", build_input_safety_subgraph(self.runtime))
        graph.add_node("triage", build_triage_subgraph(self.runtime))
        graph.add_node("clarification", build_clarification_subgraph(self.runtime))
        graph.add_node("query_understanding", build_query_understanding_subgraph(self.runtime))
        graph.add_node("retrieval", build_retrieval_subgraph(self.runtime))
        graph.add_node("evidence_verification", build_evidence_subgraph(self.runtime))
        graph.add_node("answer_generation", build_answer_subgraph(self.runtime))
        graph.add_node("output_safety", build_output_safety_subgraph(self.runtime))
        graph.add_node("human_review", build_human_review_subgraph(self.runtime))
        graph.add_node("supervisor", self._supervisor_node)
        graph.add_node("finalize", self._finalize_node)
        graph.add_node("entry", lambda state: dict(state))
        graph.add_edge(START, "entry")
        graph.add_conditional_edges(
            "entry",
            lambda state: state.get("resume_node", "input_safety"),
            {
                "input_safety": "input_safety",
                "triage": "triage",
                "clarification": "clarification",
                "query_understanding": "query_understanding",
                "retrieval": "retrieval",
                "evidence_verification": "evidence_verification",
                "answer_generation": "answer_generation",
                "output_safety": "output_safety",
                "human_review": "human_review",
                "finalize": "finalize",
            },
        )
        for node in (
            "input_safety", "triage", "clarification", "query_understanding", "retrieval",
            "evidence_verification", "answer_generation", "output_safety", "human_review", "finalize",
        ):
            graph.add_edge(node, "supervisor")
        graph.add_conditional_edges(
            "supervisor",
            lambda state: state.get("next_node", "end"),
            {
                "triage": "triage",
                "clarification": "clarification",
                "query_understanding": "query_understanding",
                "retrieval": "retrieval",
                "evidence_verification": "evidence_verification",
                "answer_generation": "answer_generation",
                "output_safety": "output_safety",
                "human_review": "human_review",
                "finalize": "finalize",
                "end": END,
            },
        )
        return graph.compile()

    def _supervisor_node(self, state: AgentGraphState) -> dict:
        updated = dict(state)
        if not updated.get("task_graph") or updated.get("current_agent") == "triage":
            updated["task_graph"] = build_minimal_task_graph(updated)
            updated["selected_agents"] = [task["agent"] for task in updated["task_graph"]]
            self.runtime.public_event(updated, "minimal_agent_team_selected", {
                "selected_agents": updated["selected_agents"],
                "task_graph": updated["task_graph"],
            })
        update_task_progress(updated)
        decision = supervisor.decide(updated, human_review_enabled=settings.ENABLE_HUMAN_REVIEW)
        if updated.get("current_agent") == "evidence_verification" and decision.next_node == "retrieval":
            updated["retrieval_retry_count"] = int(updated.get("retrieval_retry_count", 0)) + 1
        if updated.get("current_agent") == "output_safety" and decision.next_node == "answer_generation":
            updated["safety_rewrite_count"] = int(updated.get("safety_rewrite_count", 0)) + 1
        updated["next_node"] = decision.next_node
        # Early termination removes no-longer-useful work once the supervisor
        # has enough verified/safe material to finalize.
        if decision.next_node == "finalize" and updated.get("remaining_tasks"):
            final_task_ids = {task["id"] for task in updated.get("task_graph", []) if task["agent"] == "finalize"}
            updated["early_terminated"] = any(task_id not in final_task_ids for task_id in updated["remaining_tasks"])
        if decision.next_node != "end":
            updated["resume_node"] = decision.next_node
        self.runtime.public_event(updated, "supervisor_route", {
            "from": updated.get("current_agent"), "to": decision.next_node,
        })
        self.runtime.checkpoint(updated, "supervisor")
        return updated

    def _finalize_node(self, state: AgentGraphState) -> dict:
        updated = dict(state)
        direct_general_answer = bool(
            updated.get("assistant_profile") == "general_qa"
            and updated.get("intent") == "general_knowledge"
        )
        if updated.get("need_emergency_response"):
            pass
        elif updated.get("intent") == "out_of_scope":
            updated["final_answer"] = "该问题不属于医疗健康问答范围。我可以协助解释一般医学知识、药品公开信息或健康风险边界。"
        elif not direct_general_answer and updated.get("evidence_status") == "system_error":
            updated["final_answer"] = "检索系统当前不可用，无法安全地完成证据核验。请稍后重试。"
        elif not direct_general_answer and updated.get("evidence_status") == "conflicting":
            updated["final_answer"] = "检索到的医学证据存在冲突，当前无法给出单一结论。建议由专业人员审核这些来源。"
        elif not direct_general_answer and updated.get("evidence_status") in {"insufficient", "not_run"}:
            updated["final_answer"] = "目前没有足够的、经过授权和核验的医学证据回答这个问题。"
        elif updated.get("safety_status") != "pass":
            updated["final_answer"] = "该请求涉及医疗安全边界，系统未放行自动生成的答案。请咨询合格的医疗专业人员。"
        else:
            safe_candidates = [
                item for item in updated.get("answer_candidates", [])
                if item.get("safety_status") == "pass"
            ]
            if safe_candidates:
                variants = [{
                    "variant_id": item["variant_id"],
                    "style": item["style"],
                    "label": item["label"],
                    "agent_name": item["agent_name"],
                    "request_id": updated["request_id"],
                    "answer": _render_structured_answer(item["answer_draft"]),
                    "citations": item.get("citations", []),
                    "evidence_basis_id": item.get("evidence_basis_id"),
                    "evidence_ids": item.get("evidence_ids", []),
                    "evidence_count": item.get("evidence_count", 0),
                    "safety_status": item["safety_status"],
                } for item in safe_candidates]
                primary = safe_candidates[0]
                updated["answer_draft"] = primary["answer_draft"]
                updated["citations"] = primary.get("citations", [])
                updated["answer_variants"] = variants
                updated["recommended_variant_id"] = primary["variant_id"]
                updated["final_answer"] = variants[0]["answer"]
            else:
                updated["final_answer"] = _render_verified_answer(updated)
        updated["status"] = "completed"
        updated["final_evidence"] = list(updated.get("verified_evidence", []))
        update_task_progress(updated)
        updated["current_agent"] = "finalize"
        updated["next_node"] = "end"
        updated["resume_node"] = "finalize"
        self.runtime.public_event(updated, "done", {
            "status": "completed", "citation_count": len(updated.get("citations", [])),
            "variant_count": len(updated.get("answer_variants", [])),
        })
        self.runtime.checkpoint(updated, "finalize")
        if settings.ENABLE_NEW_MEMORY_ARCHITECTURE and getattr(self.runtime, "persist", False):
            # M4 stores the reusable workflow outcome, not the user's raw medical query.
            # Failure here must not invalidate a completed answer/checkpoint.
            try:
                from app.db.session import MySQLSessionLocal
                from app.services.memory_service import agent_memory_service

                db = MySQLSessionLocal()
                try:
                    agent_memory_service.record_episode(
                        db, tenant_id=updated["tenant_id"], user_id=updated["user_id"],
                        thread_id=updated["thread_id"], request_id=updated["request_id"],
                        event_type="workflow_outcome", task_type=updated.get("intent", "unknown"),
                        situation_summary=f"intent={updated.get('intent')}; risk={updated.get('risk_level')}",
                        action_summary=f"agents={','.join(updated.get('completed_agents', []))}",
                        outcome_summary=f"evidence={updated.get('evidence_status')}; safety={updated.get('safety_status')}",
                        success=updated.get("evidence_status") == "sufficient" and updated.get("safety_status") == "pass",
                        quality_score=0.9 if updated.get("safety_status") == "pass" else 0.4,
                        related_entities=[], source_run_ids=[updated["request_id"]],
                        reusable=updated.get("evidence_status") == "sufficient" and updated.get("safety_status") == "pass",
                        agent_name="supervisor",
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()
            except Exception:
                pass
        return updated

    def run(self, state: AgentGraphState) -> AgentGraphState:
        try:
            return self.graph.invoke(state, config={"recursion_limit": 40})
        except (AgentLimitExceeded, ToolLimitExceeded, TimeoutError) as exc:
            failed = dict(state)
            failed["status"] = "failed"
            code = str(exc) if str(exc) else type(exc).__name__
            self.runtime.add_error(failed, "supervisor", code, str(exc), False)
            failed["final_answer"] = "受控 Agent 工作流已安全终止，请稍后重试。"
            self.runtime.public_event(failed, "error", {"error_code": code})
            self.runtime.checkpoint(failed, "failed")
            return failed


def build_controlled_workflow(*, persist: bool = True, trace: bool = True) -> ControlledMedAgentWorkflow:
    return ControlledMedAgentWorkflow(AgentRuntimeService(persist=persist, trace=trace))
