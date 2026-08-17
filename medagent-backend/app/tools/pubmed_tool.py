"""PubMed E-utilities adapter with bounded requests and normalized evidence."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import httpx

from app.agents.schemas import RetrievedEvidence
from app.tools.online_base import online_evidence_id
from app.tools.registry import ToolDefinition, tool_registry
from app.tools.schemas import OnlineRetrievalInput, ToolExecutionResult


class PubMedTool:
    name = "pubmed"
    version = "1.0.0"
    base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=httpx.Timeout(10.0, connect=3.0))

    def execute(self, payload: OnlineRetrievalInput) -> ToolExecutionResult:
        try:
            search = self.client.get(
                f"{self.base_url}/esearch.fcgi",
                params={"db": "pubmed", "term": payload.query, "retmode": "json", "retmax": payload.max_results},
            )
            search.raise_for_status()
            ids = search.json().get("esearchresult", {}).get("idlist", [])[: payload.max_results]
            if not ids:
                return ToolExecutionResult(status="no_result")
            fetched = self.client.get(
                f"{self.base_url}/efetch.fcgi",
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "xml"},
            )
            fetched.raise_for_status()
            root = ET.fromstring(fetched.text)
            evidence = []
            for article in root.findall(".//PubmedArticle"):
                pmid = "".join(article.findtext(".//PMID", default="")).strip()
                title = "".join(article.find(".//ArticleTitle").itertext()) if article.find(".//ArticleTitle") is not None else ""
                abstract = " ".join("".join(node.itertext()) for node in article.findall(".//AbstractText"))
                content = (title + ". " + abstract).strip()
                if not pmid or not content:
                    continue
                evidence.append(RetrievedEvidence(
                    evidence_id=online_evidence_id("pubmed", pmid),
                    content=content,
                    source_type="pubmed",
                    source_name="PubMed",
                    url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    pmid=pmid,
                    authority_level=7,
                    is_authorized=True,
                    is_conversation_memory=False,
                    metadata={"pmid": pmid},
                ))
            return ToolExecutionResult(status="ok" if evidence else "no_result", evidence=evidence)
        except (httpx.HTTPError, ValueError, ET.ParseError) as exc:
            return ToolExecutionResult(status="error", error_code="PUBMED_UNAVAILABLE", message=str(exc))


pubmed_tool = PubMedTool()
tool_registry.register(ToolDefinition(
    pubmed_tool.name, pubmed_tool.version, OnlineRetrievalInput,
    description="Search NCBI PubMed for literature metadata and abstracts. Use for literature or recent-evidence intents; do not use for individual diagnosis. Live read-only external source that may return no_result.",
    category="medical_source", risk_level="medium", allowed_agents=frozenset({"query_understanding", "retrieval", "supervisor"}),
    required_scopes=frozenset({"online:read"}), timeout_seconds=12, max_retries=2,
    max_calls_per_run=2, cache_ttl_seconds=3600,
), pubmed_tool)
