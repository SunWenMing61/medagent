"""Public, budget-oriented ReAct runtime complexity monitoring."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.core.config import settings


@dataclass(slots=True)
class RuntimeComplexitySnapshot:
    step_count: int
    tool_call_count: int
    unique_tool_count: int
    repeated_tool_calls: int
    tool_failure_count: int
    remaining_subtasks: int
    rag_conflict: bool
    context_growth: int
    token_usage: int
    safety_level: str

    def as_dict(self) -> dict:
        return {name: getattr(self, name) for name in self.__slots__}


class RuntimeComplexityMonitor:
    def snapshot(self, state: dict) -> RuntimeComplexitySnapshot:
        names = list(state.get("tool_call_names", []))
        counts = Counter(names)
        return RuntimeComplexitySnapshot(
            step_count=int(state.get("react_step_count", 0)),
            tool_call_count=int(state.get("tool_call_count", 0)),
            unique_tool_count=len(counts),
            repeated_tool_calls=sum(max(0, count - 1) for count in counts.values()),
            tool_failure_count=int(state.get("tool_failure_count", 0)),
            remaining_subtasks=max(0, len(state.get("sub_questions", [])) - len(state.get("completed_tasks", []))),
            rag_conflict=state.get("evidence_status") == "conflicting" or bool(state.get("evidence_conflicts")),
            context_growth=sum(len(str(state.get(key, ""))) for key in ("retrieved_evidence", "tool_results", "conversation_summary")),
            token_usage=int(state.get("tokens_used", 0)),
            safety_level=str(state.get("risk_level", "low")),
        )

    def escalation_reason(self, state: dict) -> str | None:
        item = self.snapshot(state)
        if item.rag_conflict:
            return "conflicting_rag_evidence"
        if item.tool_failure_count >= settings.REACT_MAX_TOOL_FAILURES:
            return "consecutive_tool_failures"
        if item.repeated_tool_calls > settings.REACT_MAX_REPEATED_TOOL_CALLS:
            return "repeated_tool_loop"
        if item.unique_tool_count > settings.REACT_MAX_UNIQUE_TOOLS:
            return "multiple_dependent_tools"
        if item.tool_call_count > settings.REACT_MAX_TOOL_CALLS:
            return "tool_call_budget_exceeded"
        if item.remaining_subtasks >= 3:
            return "new_independent_subtasks"
        if item.step_count >= settings.REACT_MAX_STEPS:
            return "react_step_budget_exceeded"
        budget = min(int(state.get("token_budget", settings.REACT_MAX_TOKEN_BUDGET)), settings.REACT_MAX_TOKEN_BUDGET)
        if item.token_usage >= budget * .8:
            return "token_budget_pressure"
        if item.safety_level in {"high", "emergency"} and item.step_count > 2:
            return "safety_complexity_increased"
        return None


runtime_complexity_monitor = RuntimeComplexityMonitor()
