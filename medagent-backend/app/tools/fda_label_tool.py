"""openFDA drug-label adapter with explicit error/no-result distinction."""

from __future__ import annotations

import httpx

from app.agents.schemas import RetrievedEvidence
from app.tools.online_base import online_evidence_id
from app.tools.registry import ToolDefinition, tool_registry
from app.tools.schemas import OnlineRetrievalInput, ToolExecutionResult


class FDADrugLabelTool:
    name = "fda_drug_label"
    version = "1.0.0"
    url = "https://api.fda.gov/drug/label.json"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0))

    def execute(self, payload: OnlineRetrievalInput) -> ToolExecutionResult:
        try:
            response = self.client.get(
                self.url,
                params={"search": f'openfda.brand_name:"{payload.query}"', "limit": payload.max_results},
            )
            if response.status_code == 404:
                return ToolExecutionResult(status="no_result")
            response.raise_for_status()
            evidence = []
            for index, label in enumerate(response.json().get("results", [])):
                label_id = str(label.get("id") or label.get("set_id") or f"{payload.query}:{index}")
                sections = []
                for key in ("indications_and_usage", "warnings", "contraindications", "drug_interactions"):
                    values = label.get(key) or []
                    if values:
                        sections.append(f"{key}: {' '.join(values[:2])}")
                if not sections:
                    continue
                evidence.append(RetrievedEvidence(
                    evidence_id=online_evidence_id("openfda", label_id),
                    content="\n".join(sections),
                    source_type="fda_drug_label",
                    source_name="FDA Drug Label",
                    url=f"https://api.fda.gov/drug/label.json?search=id:{label_id}",
                    authority_level=9,
                    is_authorized=True,
                    is_conversation_memory=False,
                    metadata={"set_id": label.get("set_id"), "openfda": label.get("openfda", {})},
                ))
            return ToolExecutionResult(status="ok" if evidence else "no_result", evidence=evidence)
        except (httpx.HTTPError, ValueError) as exc:
            return ToolExecutionResult(status="error", error_code="FDA_LABEL_UNAVAILABLE", message=str(exc))


fda_label_tool = FDADrugLabelTool()
tool_registry.register(ToolDefinition(
    fda_label_tool.name, fda_label_tool.version, OnlineRetrievalInput,
    description="Retrieve structured public FDA drug-label sections. Use for indications, contraindications, warnings and interactions; do not use as a prescription. Live read-only source that may return no_result.",
    category="medical_source", risk_level="medium", allowed_agents=frozenset({"query_understanding", "retrieval", "supervisor"}),
    required_scopes=frozenset({"online:read"}), timeout_seconds=12, max_retries=2,
    max_calls_per_run=2, cache_ttl_seconds=3600,
), fda_label_tool)
