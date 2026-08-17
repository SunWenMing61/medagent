"""Deterministic policy engine evaluated before every tool invocation."""

from app.tools.registry import ToolDefinition
from app.tools.schemas import AgentRuntimeContext, ToolHealthStatus, ToolPolicyDecision


class ToolPolicyEngine:
    def decide(self, definition: ToolDefinition, context: AgentRuntimeContext, health: ToolHealthStatus, *, calls_for_tool: int) -> ToolPolicyDecision:
        if health.status in {"unavailable", "disabled"} or health.circuit_state == "open":
            return ToolPolicyDecision(enabled=False, reason=f"Tool health is {health.status}/{health.circuit_state}.", max_calls=0, fallback_tool=definition.fallback_tool)
        if "*" not in definition.allowed_agents and context.agent_name not in definition.allowed_agents:
            return ToolPolicyDecision(enabled=False, reason="The current agent is not allowed to use this tool.", max_calls=0)
        if not set(definition.required_scopes).issubset(context.permission_scopes):
            return ToolPolicyDecision(enabled=False, reason="Required runtime permission scopes are missing.", max_calls=0)
        if context.risk_level == "emergency" and definition.category not in {"safety", "workflow"}:
            return ToolPolicyDecision(enabled=False, reason="Emergency flow does not expose ordinary retrieval tools.", max_calls=0)
        if definition.category in {"web_source", "medical_source"} and not context.online_search_enabled:
            return ToolPolicyDecision(enabled=False, reason="Online search is disabled for this run.", max_calls=0)
        if context.remaining_tool_calls <= 0 or calls_for_tool >= definition.max_calls_per_run:
            return ToolPolicyDecision(enabled=False, reason="The remaining tool-call budget is exhausted.", max_calls=definition.max_calls_per_run)
        if context.remaining_token_budget <= 0:
            return ToolPolicyDecision(enabled=False, reason="The remaining token budget is exhausted.", max_calls=0)
        return ToolPolicyDecision(
            enabled=not definition.requires_approval,
            requires_approval=definition.requires_approval,
            reason="Tool is allowed by agent, scope, health, risk and budget policies.",
            max_calls=min(context.remaining_tool_calls, definition.max_calls_per_run),
            fallback_tool=definition.fallback_tool,
        )


tool_policy_engine = ToolPolicyEngine()
