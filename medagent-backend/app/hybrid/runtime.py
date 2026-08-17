"""Top-level hybrid runtime choosing ReAct or controlled multi-agent execution."""

from __future__ import annotations

import time

from app.graphs.root_graph import ControlledMedAgentWorkflow
from app.hybrid.complexity_router import complexity_router
from app.hybrid.contracts import EscalationRequired, ExecutionMode
from app.hybrid.direct_runtime import DirectRuntime
from app.hybrid.react_runtime import ReActRuntime
from app.services.agent_runtime_service import AgentRuntimeService


class HybridAgentRuntime:
    def __init__(self, *, persist: bool = True, trace: bool = True, router=complexity_router, runtime=None) -> None:
        self.router = router
        self.runtime = runtime or AgentRuntimeService(persist=persist, trace=trace)

    def run(self, state: dict) -> dict:
        started = time.perf_counter()
        decision = self.router.route(state.get("raw_query", ""), conversation_summary=state.get("conversation_summary", ""))
        updated = dict(state)
        updated["initial_execution_mode"] = decision.execution_mode.value
        updated["execution_mode"] = decision.execution_mode.value
        updated["complexity_level"] = decision.complexity_level.value
        updated["router"] = decision.as_dict()
        updated["escalated"] = False
        updated["escalation_reason"] = None
        self.runtime.public_event(updated, "complexity_routed", decision.as_dict())
        if decision.execution_mode == ExecutionMode.DIRECT:
            result = DirectRuntime(self.runtime).run(updated)
        elif decision.execution_mode == ExecutionMode.MULTI_AGENT:
            result = ControlledMedAgentWorkflow(self.runtime).run(updated)
        else:
            try:
                result = ReActRuntime(self.runtime).run(updated, escalation_enabled=decision.escalation_enabled)
            except EscalationRequired as exc:
                escalated = dict(exc.state)
                escalated["execution_mode"] = ExecutionMode.REACT_ESCALATED_TO_MULTI_AGENT.value
                escalated["escalated"] = True
                escalated["escalation_reason"] = exc.reason
                self.runtime.public_event(escalated, "execution_escalated", {"reason": exc.reason})
                result = ControlledMedAgentWorkflow(self.runtime).run(escalated)
        result["hybrid_latency_ms"] = round((time.perf_counter() - started) * 1000, 3)
        result.setdefault("router", decision.as_dict())
        result["execution_trace"] = {
            "execution_mode": result.get("execution_mode"),
            "complexity_level": result.get("complexity_level"),
            "complexity_score": decision.score,
            "router_confidence": decision.confidence,
            "router_signals": decision.signals,
            "router_latency": decision.latency_ms,
            "router_tokens": decision.input_tokens + decision.output_tokens,
            "escalated": bool(result.get("escalated")),
            "escalation_reason": result.get("escalation_reason"),
            "agent_count": len(set(result.get("completed_agents", []))),
            "agent_handoff_count": max(0, len(result.get("completed_agents", [])) - 1),
            "step_count": int(result.get("react_step_count", 0)),
            "tool_call_count": int(result.get("tool_call_count", 0)),
            "unique_tool_count": len(set(result.get("tool_call_names", []))),
            "retrieval_count": len(result.get("retrieved_evidence", [])),
            "llm_call_count": int(result.get("agent_call_count", 0)),
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": int(result.get("tokens_used", 0)),
            "estimated_cost": 0.0,
            "latency": result["hybrid_latency_ms"],
        }
        return result


hybrid_agent_runtime = HybridAgentRuntime()
