"""Two-stage deterministic candidate filtering before any Agent tool choice."""

from app.tools.health import tool_health_manager
from app.tools.registry import tool_registry


INTENT_TO_TOOLS = {
    "general_knowledge": ["local_knowledge_base", "web_search"],
    "drug_information": ["local_knowledge_base", "fda_drug_label", "msd_manual"],
    "literature_search": ["pubmed", "local_knowledge_base"],
    "document_summary": ["local_knowledge_base", "get_document_evidence_context", "get_medical_table"],
    "medical_knowledge": ["local_knowledge_base", "msd_manual"],
    "symptom_consultation": ["local_knowledge_base"],
    "emergency_risk": [],
    "out_of_scope": [],
}


def select_tool_candidates(intent: str, *, agent_name: str, permission_scopes: set[str], risk_level: str, online_enabled: bool) -> list[str]:
    if risk_level == "emergency":
        return []
    selected: list[str] = []
    for name in INTENT_TO_TOOLS.get(intent, ["local_knowledge_base"]):
        try:
            definition, _ = tool_registry.get(name)
        except KeyError:
            continue
        if definition.category in {"web_source", "medical_source"} and not online_enabled:
            continue
        if "*" not in definition.allowed_agents and agent_name not in definition.allowed_agents:
            continue
        if not set(definition.required_scopes).issubset(permission_scopes):
            continue
        health = tool_health_manager.status(name)
        if health.status in {"unavailable", "disabled"} or health.circuit_state == "open":
            if definition.fallback_tool and definition.fallback_tool not in selected:
                selected.append(definition.fallback_tool)
            continue
        selected.append(name)
        if len(selected) == 4:
            break
    return selected
