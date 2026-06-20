"""MSD Manuals (默沙东诊疗手册) adapter using web scraping.

Scrapes the Chinese professional edition at https://www.msdmanuals.cn/professional/
Content is organized in a tree: Section → Chapter → Topic.
"""

import re
import time
from typing import AsyncGenerator, Optional

import httpx
from bs4 import BeautifulSoup

from app.adapters.base import BaseSourceAdapter, SourceDocument
from app.adapters import register_adapter


MSD_BASE = "https://www.msdmanuals.cn"
MSD_PROFESSIONAL = f"{MSD_BASE}/professional"


class MSDManualAdapter(BaseSourceAdapter):
    source_type = "msd_manual"
    display_name = "默沙东诊疗手册"

    def __init__(self):
        self._last_request_time = 0.0

    def _rate_limit(self, delay_ms: int = 1500):
        """Respectful delay between requests."""
        min_interval = delay_ms / 1000.0
        elapsed = time.time() - self._last_request_time
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()

    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        max_topics = config.get("max_topics", 200)
        if not isinstance(max_topics, int) or max_topics < 1 or max_topics > 5000:
            return False, "max_topics 必须在 1-5000 之间"
        delay = config.get("request_delay_ms", 1500)
        if delay < 200 or delay > 10000:
            return False, "请求延迟必须在 200-10000ms 之间"
        return True, None

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "title": "默沙东诊疗手册配置",
            "properties": {
                "max_topics": {
                    "type": "integer",
                    "title": "最大主题数",
                    "description": "每次同步获取的最大主题数量",
                    "default": 200,
                    "minimum": 1,
                    "maximum": 5000,
                },
                "include_full_text": {
                    "type": "boolean",
                    "title": "获取全文",
                    "description": "是否获取完整正文内容（否则只获取引言段落）",
                    "default": True,
                },
                "request_delay_ms": {
                    "type": "integer",
                    "title": "请求间隔 (毫秒)",
                    "description": "每次 HTTP 请求之间的等待时间",
                    "default": 1500,
                    "minimum": 200,
                    "maximum": 10000,
                },
                "version": {
                    "type": "string",
                    "title": "版本",
                    "enum": ["professional", "home"],
                    "enumNames": ["专业版", "大众版"],
                    "default": "professional",
                },
            },
            "required": [],
        }

    def get_default_config(self) -> dict:
        return {
            "max_topics": 200,
            "include_full_text": True,
            "request_delay_ms": 1500,
            "version": "professional",
        }

    async def _fetch_soup(self, client: httpx.AsyncClient, url: str, delay_ms: int) -> Optional[BeautifulSoup]:
        """Fetch a URL and return parsed BeautifulSoup, with rate limiting."""
        self._rate_limit(delay_ms)
        try:
            resp = await client.get(url, follow_redirects=True, timeout=30)
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except Exception:
            return None

    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        max_topics = int(config.get("max_topics", 200))
        include_full_text = config.get("include_full_text", True)
        delay_ms = int(config.get("request_delay_ms", 1500))
        version = config.get("version", "professional")

        base_url = f"{MSD_BASE}/{version}" if version == "professional" else f"{MSD_BASE}/home"

        topic_count = 0
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Get the homepage to discover sections
            soup = await self._fetch_soup(client, base_url, delay_ms)
            if soup is None:
                return

            # Discover section links from the TOC or sidebar
            section_urls = self._extract_section_urls(soup, base_url)
            if not section_urls:
                # Fallback: try common selectors
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if f"/{version}/" in href and not href.startswith("http"):
                        href = f"{MSD_BASE}{href}"
                    if href not in section_urls:
                        section_urls.append(href)

            for section_url in section_urls:
                if topic_count >= max_topics:
                    break

                soup = await self._fetch_soup(client, section_url, delay_ms)
                if soup is None:
                    continue

                # Extract topic links from the chapter/toc
                topic_urls = self._extract_topic_urls(soup, base_url)
                for topic_url in topic_urls:
                    if topic_count >= max_topics:
                        break

                    soup = await self._fetch_soup(client, topic_url, delay_ms)
                    if soup is None:
                        continue

                    doc = self._parse_topic(soup, topic_url, include_full_text)
                    if doc is not None:
                        topic_count += 1
                        yield doc

    def _extract_section_urls(self, soup: BeautifulSoup, base_url: str) -> list:
        """Discover section/chapter URLs from the navigation."""
        urls = []
        seen = set()

        # Try various navigation selectors used by MSD Manuals
        selectors = [
            "nav a[href]",
            ".toc a[href]",
            ".nav-toc a[href]",
            ".sidebar-nav a[href]",
            "[data-testid='toc'] a[href]",
            ".navigation a[href]",
        ]

        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href", "")
                if href.startswith("/"):
                    href = f"{MSD_BASE}{href}"
                if base_url in href and href not in seen:
                    seen.add(href)
                    urls.append(href)

        return urls

    def _extract_topic_urls(self, soup: BeautifulSoup, base_url: str) -> list:
        """Extract topic (article) URLs from a chapter page."""
        urls = []
        seen = set()

        selectors = [
            ".topic-list a[href]",
            ".article-list a[href]",
            ".content-list a[href]",
            "main a[href]",
            "[data-testid='topic-list'] a[href]",
            "ul li a[href]",
        ]

        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href", "")
                if not href or "#" in href:
                    continue
                if href.startswith("/"):
                    href = f"{MSD_BASE}{href}"
                if base_url in href and href not in seen:
                    seen.add(href)
                    urls.append(href)

        return urls

    def _parse_topic(
        self, soup: BeautifulSoup, url: str, include_full_text: bool,
    ) -> Optional[SourceDocument]:
        """Parse a single topic page into a SourceDocument."""
        # Title
        title_el = (
            soup.find("h1")
            or soup.find("[data-testid='page-title']")
            or soup.find("title")
        )
        if title_el is None:
            return None
        title = title_el.get_text(strip=True)

        # Remove suffix from title
        for suffix in [" - MSD诊疗手册专业版", " - 默沙东诊疗手册", " | MSD Manuals"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)]

        # Content
        content_parts = []

        # Try main content area
        main_selectors = [
            "main",
            "[role='main']",
            ".content-body",
            ".article-content",
            ".topic-content",
            "#content",
            "article",
        ]

        content_el = None
        for sel in main_selectors:
            el = soup.select_one(sel)
            if el:
                content_el = el
                break

        if content_el is None:
            # Try to extract from body
            content_el = soup.find("body")

        if content_el is None:
            return None

        # Remove unwanted elements
        for tag in content_el.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Extract headings and paragraphs
        for elem in content_el.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            text = elem.get_text(strip=True)
            if text and len(text) > 5:
                if elem.name.startswith("h"):
                    content_parts.append(f"\n## {text}\n")
                elif elem.name == "li":
                    content_parts.append(f"- {text}")
                else:
                    content_parts.append(text)

        full_content = "\n\n".join(content_parts)

        if not full_content.strip():
            return None

        # Clean up whitespace
        full_content = re.sub(r"\n{3,}", "\n\n", full_content).strip()

        # If not full text, just take first ~500 chars as intro
        if not include_full_text:
            full_content = full_content[:500]

        # Get breadcrumbs for context
        breadcrumbs = []
        for crumb in soup.select("[class*='breadcrumb'] a"):
            text = crumb.get_text(strip=True)
            if text:
                breadcrumbs.append(text)

        return SourceDocument(
            title=title,
            content=full_content,
            source_url=url,
            source_id_field=url,
            metadata={
                "breadcrumbs": breadcrumbs,
                "version": "professional",
                "section": breadcrumbs[0] if breadcrumbs else "",
            },
        )


register_adapter(MSDManualAdapter)
