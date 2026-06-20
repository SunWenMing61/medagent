"""Utility for performing web searches and formatting results."""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

SEARCH_RESULT_COUNT = 5


def search_web(query: str, api_key: Optional[str] = None, api_base: str = "https://google.serper.dev") -> List[dict]:
    """Search the web via a Serper.dev-compatible API and return result snippets.

    Each result dict has keys: title, snippet, link.
    Returns empty list on failure or if no API key configured.
    """
    if not api_key:
        logger.warning("SEARCH_API_KEY not configured — web search unavailable")
        return []

    import httpx

    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{api_base}/search",
                headers={
                    "X-API-KEY": api_key,
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": SEARCH_RESULT_COUNT},
            )
            response.raise_for_status()
            data = response.json()

            results = []
            for item in data.get("organic", []):
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": item.get("link", ""),
                })
            return results
    except Exception as e:
        logger.error("Web search failed: %s", e)
        return []


def format_search_results(results: List[dict]) -> str:
    """Format search results for inclusion in LLM prompt context."""
    if not results:
        return ""
    parts = ["🌐 **来自网络搜索结果:**"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        link = r.get("link", "")
        parts.append(f"**{i}. {title}**")
        if snippet:
            parts.append(f"   {snippet}")
        if link:
            parts.append(f"   来源: {link}")
    return "\n\n".join(parts)
