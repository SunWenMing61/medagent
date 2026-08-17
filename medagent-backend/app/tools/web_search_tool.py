"""Generic web-search adapter with a keyless public fallback.

Serper is used when ``SEARCH_API_KEY`` is configured. Otherwise the tool uses
DuckDuckGo's Instant Answer API and then Wikipedia's public search API. All
results are normalized into the same evidence contract as local retrieval.
"""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlparse

import httpx

from app.agents.schemas import RetrievedEvidence
from app.core.config import settings
from app.tools.online_base import online_evidence_id
from app.tools.registry import ToolDefinition, tool_registry
from app.tools.schemas import OnlineRetrievalInput, ToolExecutionResult


def _public_url(value: object) -> str:
    url = str(value or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return url


def _flatten_related(items: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for item in items:
        if isinstance(item.get("Topics"), list):
            flattened.extend(_flatten_related(item["Topics"]))
        elif item.get("Text") and item.get("FirstURL"):
            flattened.append({
                "title": str(item["Text"]).split(" - ", 1)[0],
                "snippet": str(item["Text"]),
                "link": item["FirstURL"],
                "provider": "duckduckgo",
            })
    return flattened


def _duckduckgo_target(value: object) -> str:
    url = str(value or "").strip()
    if url.startswith("//"):
        url = "https:" + url
    parsed = urlparse(url)
    redirected = parse_qs(parsed.query).get("uddg") if "duckduckgo.com" in parsed.netloc else None
    return str(redirected[0]) if redirected else url


class _DuckDuckGoHTMLParser(HTMLParser):
    """Extract result titles, snippets and decoded target URLs without extra dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict] = []
        self._capture: str | None = None
        self._depth = 0
        self._buffer: list[str] = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set(str(attributes.get("class") or "").split())
        if self._capture:
            self._depth += 1
            return
        if tag == "a" and "result__a" in classes:
            self._capture, self._depth, self._buffer = "title", 1, []
            self._href = _duckduckgo_target(attributes.get("href"))
        elif "result__snippet" in classes:
            self._capture, self._depth, self._buffer = "snippet", 1, []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        del tag
        if not self._capture:
            return
        self._depth -= 1
        if self._depth > 0:
            return
        value = " ".join("".join(self._buffer).split())
        if self._capture == "title" and self._href:
            self.results.append({
                "title": value,
                "snippet": "",
                "link": self._href,
                "provider": "duckduckgo_html",
            })
        elif self._capture == "snippet" and self.results and not self.results[-1]["snippet"]:
            self.results[-1]["snippet"] = value
        self._capture, self._depth, self._buffer, self._href = None, 0, [], ""


class WebSearchTool:
    name = "web_search"
    version = "1.0.0"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(
            timeout=httpx.Timeout(10.0, connect=3.0),
            follow_redirects=True,
            headers={"User-Agent": "MedAgent/1.0 (+public read-only search)"},
        )

    def execute(self, payload: OnlineRetrievalInput) -> ToolExecutionResult:
        warnings: list[str] = []
        raw_results: list[dict] = []

        if settings.SEARCH_API_KEY:
            try:
                raw_results = self._serper(payload.query, payload.max_results)
            except (httpx.HTTPError, ValueError) as exc:
                warnings.append(f"Configured search provider unavailable: {exc}")

        if not raw_results:
            try:
                raw_results = self._duckduckgo(payload.query, payload.max_results)
            except (httpx.HTTPError, ValueError) as exc:
                warnings.append(f"DuckDuckGo fallback unavailable: {exc}")

        if not raw_results:
            try:
                raw_results = self._wikipedia(payload.query, payload.max_results)
            except (httpx.HTTPError, ValueError) as exc:
                warnings.append(f"Wikipedia fallback unavailable: {exc}")

        evidence: list[RetrievedEvidence] = []
        seen: set[str] = set()
        for item in raw_results:
            url = _public_url(item.get("link"))
            title = str(item.get("title") or "").strip()
            snippet = str(item.get("snippet") or "").strip()
            if not url or not (title or snippet) or url in seen:
                continue
            seen.add(url)
            provider = str(item.get("provider") or "web")
            domain = (urlparse(url).hostname or provider).removeprefix("www.")
            evidence.append(RetrievedEvidence(
                evidence_id=online_evidence_id("web", url),
                content=f"{title}. {snippet}".strip(" ."),
                source_type="web_search",
                source_name=f"互联网 · {domain}",
                url=url,
                retrieval_score=max(0.35, 0.72 - len(evidence) * 0.05),
                authority_level=self._authority(domain),
                is_authorized=True,
                is_conversation_memory=False,
                metadata={"title": title, "provider": provider, "domain": domain},
            ))
            if len(evidence) >= payload.max_results:
                break

        if evidence:
            return ToolExecutionResult(status="success", evidence=evidence, warnings=warnings)
        if warnings:
            return ToolExecutionResult(
                status="error",
                error_code="WEB_SEARCH_UNAVAILABLE",
                message="; ".join(warnings),
                warnings=warnings,
            )
        return ToolExecutionResult(status="no_result", warnings=["No public web results matched the query."])

    def _serper(self, query: str, max_results: int) -> list[dict]:
        response = self.client.post(
            f"{settings.SEARCH_API_BASE.rstrip('/')}/search",
            headers={"X-API-KEY": settings.SEARCH_API_KEY, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
        )
        response.raise_for_status()
        return [
            {
                "title": item.get("title"),
                "snippet": item.get("snippet"),
                "link": item.get("link"),
                "provider": "serper",
            }
            for item in response.json().get("organic", [])[:max_results]
        ]

    def _duckduckgo(self, query: str, max_results: int) -> list[dict]:
        response = self.client.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
        )
        response.raise_for_status()
        data = response.json()
        results: list[dict] = []
        if data.get("AbstractText") and data.get("AbstractURL"):
            results.append({
                "title": data.get("Heading") or query,
                "snippet": data["AbstractText"],
                "link": data["AbstractURL"],
                "provider": "duckduckgo",
            })
        results.extend(_flatten_related(data.get("RelatedTopics") or []))
        if len(results) < max_results:
            try:
                html_response = self.client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; MedAgent/1.0)"},
                )
                html_response.raise_for_status()
                parser = _DuckDuckGoHTMLParser()
                parser.feed(html_response.text)
                known = {str(item.get("link")) for item in results}
                results.extend(item for item in parser.results if item.get("link") not in known)
            except (httpx.HTTPError, ValueError):
                if not results:
                    raise
        return results[:max_results]

    def _wikipedia(self, query: str, max_results: int) -> list[dict]:
        language = "zh" if any("\u4e00" <= char <= "\u9fff" for char in query) else "en"
        response = self.client.get(
            f"https://{language}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": max_results,
                "prop": "extracts|info",
                "exintro": 1,
                "explaintext": 1,
                "inprop": "url",
                "format": "json",
                "formatversion": 2,
                "redirects": 1,
            },
        )
        response.raise_for_status()
        pages = response.json().get("query", {}).get("pages", [])
        return [
            {
                "title": page.get("title"),
                "snippet": str(page.get("extract") or "")[:1200],
                "link": page.get("fullurl"),
                "provider": "wikipedia",
            }
            for page in pages[:max_results]
        ]

    @staticmethod
    def _authority(domain: str) -> int:
        if domain.endswith((".gov", ".gov.cn", ".edu", ".edu.cn")):
            return 7
        if domain.endswith(("wikipedia.org", ".org")):
            return 5
        return 4


web_search_tool = WebSearchTool()
tool_registry.register(
    ToolDefinition(
        web_search_tool.name,
        web_search_tool.version,
        OnlineRetrievalInput,
        description=(
            "Search the public web for general QA, returning titled URL snippets as normalized evidence. "
            "Use alongside authorized local KB retrieval; results remain untrusted until evidence verification."
        ),
        category="web_source",
        risk_level="medium",
        allowed_agents=frozenset({"query_understanding", "retrieval", "supervisor"}),
        required_scopes=frozenset({"online:read"}),
        timeout_seconds=12,
        max_retries=1,
        max_calls_per_run=2,
        cache_ttl_seconds=900,
    ),
    web_search_tool,
)
