"""PubMed adapter using NCBI E-utilities API."""

import asyncio
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

import httpx

from app.adapters.base import BaseSourceAdapter, SourceDocument
from app.adapters import register_adapter


PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class PubMedAdapter(BaseSourceAdapter):
    source_type = "pubmed"
    display_name = "PubMed"

    def __init__(self):
        self._last_request_time = 0.0
        self._client = httpx.AsyncClient(timeout=30)

    async def _rate_limit(self, api_key: str = ""):
        """NCBI rate limits: 3 req/s without API key, 10 req/s with."""
        # Use conservative intervals to avoid 429
        min_interval = 0.35 if api_key else 1.0
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an HTTP request with retry on 429."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self._client.request(method, url, **kwargs)
                if response.status_code == 429:
                    wait = 5 * (attempt + 1)
                    print(f"PubMed 429 rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                    continue
                response.raise_for_status()
                return response
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(2 * (attempt + 1))
        raise RuntimeError(f"Request failed after {max_retries} retries")

    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        if not config.get("query", "").strip():
            return False, "查询关键词 (query) 不能为空"
        max_results = config.get("max_results", 10)
        if not isinstance(max_results, int) or max_results < 1 or max_results > 1000:
            return False, "max_results 必须在 1-1000 之间"
        date_from = config.get("date_from")
        if date_from:
            try:
                datetime.strptime(date_from, "%Y-%m-%d")
            except ValueError:
                return False, "date_from 格式应为 YYYY-MM-DD"
        return True, None

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "title": "PubMed 配置",
            "properties": {
                "query": {
                    "type": "string",
                    "title": "检索关键词",
                    "description": "PubMed 检索式，如 'hypertension treatment'",
                    "minLength": 1,
                    "maxLength": 300,
                },
                "max_results": {
                    "type": "integer",
                    "title": "最大结果数",
                    "description": "每次同步获取的最大文献数量",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "sort_by": {
                    "type": "string",
                    "title": "排序方式",
                    "enum": ["relevance", "date_desc", "date_asc"],
                    "enumNames": ["相关度", "日期从新到旧", "日期从旧到新"],
                    "default": "relevance",
                },
                "date_from": {
                    "type": "string",
                    "title": "起始日期",
                    "description": "筛选文献的起始日期 (可选)，格式 YYYY-MM-DD",
                    "format": "date",
                },
                "date_to": {
                    "type": "string",
                    "title": "结束日期",
                    "description": "筛选文献的结束日期 (可选)，格式 YYYY-MM-DD",
                    "format": "date",
                },
                "api_key": {
                    "type": "string",
                    "title": "NCBI API Key",
                    "description": "可选，有 Key 可提升限频至 10 req/s",
                },
            },
            "required": ["query"],
        }

    def get_default_config(self) -> dict:
        return {
            "query": "",
            "max_results": 10,
            "sort_by": "relevance",
            "date_from": "",
            "date_to": "",
            "api_key": "",
        }

    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        query = config.get("query", "").strip()
        max_results = int(config.get("max_results", 10))
        sort_by = config.get("sort_by", "relevance")
        date_from = config.get("date_from", "")
        date_to = config.get("date_to", "")
        api_key = config.get("api_key", "")

        # Build date filter
        date_filter = ""
        if date_from and date_to:
            date_filter = f" AND ({date_from}[Date - Publication] : {date_to}[Date - Publication])"
        elif date_from:
            date_filter = f" AND {date_from}[Date - Publication] : 3000[Date - Publication]"
        elif date_to:
            date_filter = f" AND 1800[Date - Publication] : {date_to}[Date - Publication]"

        full_query = f"({query}){date_filter}"

        sort_map = {
            "relevance": "relevance",
            "date_desc": "pub_date",
            "date_asc": "pub_date",
        }
        ncbi_sort = sort_map.get(sort_by, "relevance")

        # Step 1: ESearch
        await self._rate_limit(api_key)
        search_params = {
            "db": "pubmed",
            "term": full_query,
            "retmax": str(max_results),
            "retmode": "json",
            "sort": ncbi_sort,
            "retstart": "0",
        }
        if api_key:
            search_params["api_key"] = api_key

        resp = await self._request_with_retry("GET", PUBMED_ESEARCH, params=search_params)
        search_data = resp.json()

        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        if not id_list:
            return

        # Step 2: EFetch in batches of 10 (reduce batch size to avoid rate limits)
        batch_size = 10
        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]
            ids_str = ",".join(batch)

            await self._rate_limit(api_key)
            fetch_params = {
                "db": "pubmed",
                "id": ids_str,
                "retmode": "xml",
                "rettype": "abstract",
            }
            if api_key:
                fetch_params["api_key"] = api_key

            resp = await self._request_with_retry("GET", PUBMED_EFETCH, params=fetch_params)
            xml_data = resp.text

            try:
                root = ET.fromstring(xml_data)
            except ET.ParseError:
                continue

            for article in root.iter("PubmedArticle"):
                medline = article.find(".//MedlineCitation")
                if medline is None:
                    continue

                article_data = medline.find("Article")
                if article_data is None:
                    continue

                # Title
                title_el = article_data.find("ArticleTitle")
                title = "".join(title_el.itertext()) if title_el is not None else "Untitled"
                if title and title.startswith("["):
                    title = title.strip("[]")

                # Abstract
                abstract_el = article_data.find("Abstract")
                content_parts = []
                if abstract_el is not None:
                    for at in abstract_el.iter("AbstractText"):
                        label = at.get("Label", "")
                        text = "".join(at.itertext()).strip()
                        if label:
                            content_parts.append(f"{label}: {text}")
                        else:
                            content_parts.append(text)
                content = "\n\n".join(content_parts) if content_parts else ""
                if not content:
                    continue

                # Authors
                author_list = article_data.find("AuthorList")
                authors = []
                if author_list is not None:
                    for author in author_list.findall("Author"):
                        last = author.find("LastName")
                        fore = author.find("ForeName")
                        if last is not None and fore is not None:
                            authors.append(f"{fore.text} {last.text}")
                        elif last is not None:
                            authors.append(last.text)

                # PMID
                pmid_el = medline.find("PMID")
                pmid = pmid_el.text if pmid_el is not None else ""

                # Publication date
                pub_date = None
                article_date = article_data.find(".//PubMedPubDate[@PubStatus='pubmed']")
                if article_date is None:
                    article_date = article_data.find(".//PubMedPubDate[@PubStatus='entrez']")
                if article_date is not None:
                    year = article_date.find("Year")
                    month = article_date.find("Month")
                    day = article_date.find("Day")
                    try:
                        y = int(year.text) if year is not None else 1970
                        m = int(month.text) if month is not None else 1
                        d = int(day.text) if day is not None else 1
                        pub_date = datetime(y, m, d, tzinfo=timezone.utc)
                    except (ValueError, TypeError):
                        pass

                # Journal
                journal_el = article_data.find("Journal/Title")
                journal = "".join(journal_el.itertext()) if journal_el is not None else ""

                # DOI
                doi_el = article.find(".//ArticleId[@IdType='doi']")
                doi = doi_el.text if doi_el is not None else ""

                article_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

                metadata = {
                    "pmid": pmid,
                    "doi": doi,
                    "journal": journal,
                    "authors": authors[:5],
                    "author_count": len(authors),
                }

                yield SourceDocument(
                    title=title.strip(),
                    content=content.strip(),
                    source_url=article_url,
                    source_id_field=pmid,
                    authors=authors,
                    publication_date=pub_date,
                    metadata=metadata,
                )


register_adapter(PubMedAdapter)
