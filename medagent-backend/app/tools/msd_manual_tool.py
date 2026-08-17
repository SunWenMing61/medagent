"""MSD Manual domain-search adapter using the configured search provider."""

from __future__ import annotations

import httpx

from app.agents.schemas import RetrievedEvidence
from app.core.config import settings
from app.tools.online_base import online_evidence_id
from app.tools.registry import ToolDefinition, tool_registry
from app.tools.schemas import OnlineRetrievalInput, ToolExecutionResult


class MSDManualTool:
    name = "msd_manual"
    version = "1.0.0"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0))

    def execute(self, payload: OnlineRetrievalInput) -> ToolExecutionResult:
        if not settings.SEARCH_API_KEY:
            return ToolExecutionResult(
                status="error", error_code="MSD_SEARCH_NOT_CONFIGURED",
                message="The MSD domain-search provider is not configured.",
            )
        try:
            response = self.client.post(
                f"{settings.SEARCH_API_BASE.rstrip('/')}/search",
                headers={"X-API-KEY": settings.SEARCH_API_KEY, "Content-Type": "application/json"},
                json={"q": f"site:msdmanuals.com {payload.query}", "num": payload.max_results},
            )
            response.raise_for_status()
            evidence = []
            for item in response.json().get("organic", [])[: payload.max_results]:
                url = str(item.get("link") or "")
                if "msdmanuals.com" not in url:
                    continue
                evidence.append(RetrievedEvidence(
                    evidence_id=online_evidence_id("msd", url),
                    content=f"{item.get('title', '')}. {item.get('snippet', '')}".strip(),
                    source_type="msd_manual",
                    source_name="MSD Manual",
                    url=url,
                    authority_level=7,
                    is_authorized=True,
                    is_conversation_memory=False,
                    metadata={},
                ))
            return ToolExecutionResult(status="ok" if evidence else "no_result", evidence=evidence)
        except (httpx.HTTPError, ValueError) as exc:
            return ToolExecutionResult(status="error", error_code="MSD_SEARCH_UNAVAILABLE", message=str(exc))


msd_manual_tool = MSDManualTool()
tool_registry.register(ToolDefinition(
    msd_manual_tool.name, msd_manual_tool.version, OnlineRetrievalInput,
    description="Search MSD Manual pages for general disease education. Use for explanatory medical background; do not use as the latest guideline or an individual diagnosis. Live read-only source and may return no_result.",
    category="medical_source", risk_level="medium", allowed_agents=frozenset({"query_understanding", "retrieval", "supervisor"}),
    required_scopes=frozenset({"online:read"}), timeout_seconds=12, max_retries=2,
    max_calls_per_run=2, cache_ttl_seconds=3600,
), msd_manual_tool)
