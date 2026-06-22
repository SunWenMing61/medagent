"""PubMed 适配器,使用 NCBI E-utilities API 获取文献数据。"""

import asyncio  # 异步 I/O,用于频率限制控制
import json    # JSON 解析(虽然此处未直接使用,但为 httpx 依赖)
import xml.etree.ElementTree as ET  # XML 解析,用于解析 PubMed EFetch 返回的 XML
from datetime import datetime, timezone  # 日期时间处理,用于出版日期
from typing import AsyncGenerator, Optional  # 异步生成器和可选类型

import httpx  # HTTP 异步客户端

from app.adapters.base import BaseSourceAdapter, SourceDocument  # 基础适配器和文档类型
from app.adapters import register_adapter  # 适配器注册函数

# NCBI E-utilities API 端点
PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"  # 文献搜索接口
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"    # 文献详情获取接口


class PubMedAdapter(BaseSourceAdapter):
    """PubMed 文献检索适配器,通过 NCBI E-utilities API 获取文献摘要。"""
    source_type = "pubmed"    # 来源类型标识
    display_name = "PubMed"   # 显示名称

    def __init__(self):
        self._last_request_time = 0.0  # 上次请求时间,用于频率限制
        self._client = httpx.AsyncClient(timeout=30)  # 创建异步 HTTP 客户端,30 秒超时

    async def _rate_limit(self, api_key: str = ""):
        """NCBI 频率限制:无 API Key 每秒最多 3 次请求,有 Key 每秒最多 10 次。

        Args:
            api_key: 可选 NCBI API Key,有 Key 时可缩短请求间隔
        """
        min_interval = 0.35 if api_key else 1.0  # 有 Key 则 350ms 间隔,否则 1 秒
        now = asyncio.get_event_loop().time()  # 获取事件循环当前时间
        elapsed = now - self._last_request_time  # 计算距上次请求的时间差
        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)  # 间隔不足则等待
        self._last_request_time = asyncio.get_event_loop().time()  # 更新请求时间

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """带重试机制的 HTTP 请求,遇到 429(限流)时自动重试。

        Args:
            method: HTTP 方法(GET/POST)
            url: 请求 URL
            **kwargs: 传递给 httpx 的额外参数

        Returns:
            httpx.Response 对象

        Raises:
            RuntimeError: 重试耗尽后仍然失败
        """
        max_retries = 3  # 最大重试次数
        for attempt in range(max_retries):
            try:
                response = await self._client.request(method, url, **kwargs)  # 发送请求
                if response.status_code == 429:
                    # 遇到 429(Too Many Requests),等待后重试
                    wait = 5 * (attempt + 1)  # 等待时间:5s, 10s, 15s
                    print(f"PubMed 429 rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)  # 等待
                    continue  # 重试
                response.raise_for_status()  # 检查其他错误状态码
                return response
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                # 超时或连接错误时也重试
                if attempt == max_retries - 1:
                    raise  # 最后一次重试仍失败则抛出异常
                await asyncio.sleep(2 * (attempt + 1))  # 递增等待:2s, 4s, 6s
        raise RuntimeError(f"Request failed after {max_retries} retries")  # 超过重试次数

    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        """验证配置:确保有搜索关键词、max_results 在范围内、日期格式正确。

        Args:
            config: 配置字典

        Returns:
            (is_valid, error_message) 元组
        """
        if not config.get("query", "").strip():
            return False, "查询关键词 (query) 不能为空"  # 搜索词必填
        max_results = config.get("max_results", 10)
        if not isinstance(max_results, int) or max_results < 1 or max_results > 1000:
            return False, "max_results 必须在 1-1000 之间"  # 结果数量超出范围
        date_from = config.get("date_from")
        if date_from:
            try:
                datetime.strptime(date_from, "%Y-%m-%d")  # 验证日期格式
            except ValueError:
                return False, "date_from 格式应为 YYYY-MM-DD"
        return True, None

    def get_config_schema(self) -> dict:
        """返回前端渲染配置表单所需的 JSON Schema。

        Returns:
            JSON Schema 字典
        """
        return {
            "type": "object",
            "title": "PubMed 配置",
            "properties": {
                "query": {                    # 检索关键词
                    "type": "string",
                    "title": "检索关键词",
                    "description": "PubMed 检索式，如 'hypertension treatment'",
                    "minLength": 1,
                    "maxLength": 300,
                },
                "max_results": {               # 最大结果数
                    "type": "integer",
                    "title": "最大结果数",
                    "description": "每次同步获取的最大文献数量",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "sort_by": {                   # 排序方式
                    "type": "string",
                    "title": "排序方式",
                    "enum": ["relevance", "date_desc", "date_asc"],
                    "enumNames": ["相关度", "日期从新到旧", "日期从旧到新"],
                    "default": "relevance",
                },
                "date_from": {                 # 起始日期筛选
                    "type": "string",
                    "title": "起始日期",
                    "description": "筛选文献的起始日期 (可选)，格式 YYYY-MM-DD",
                    "format": "date",
                },
                "date_to": {                   # 结束日期筛选
                    "type": "string",
                    "title": "结束日期",
                    "description": "筛选文献的结束日期 (可选)，格式 YYYY-MM-DD",
                    "format": "date",
                },
                "api_key": {                   # NCBI API Key(可选,可提升限频)
                    "type": "string",
                    "title": "NCBI API Key",
                    "description": "可选，有 Key 可提升限频至 10 req/s",
                },
            },
            "required": ["query"],  # 仅搜索词为必填
        }

    def get_default_config(self) -> dict:
        """返回默认配置值。"""
        return {
            "query": "",            # 搜索词默认为空
            "max_results": 10,      # 默认最多返回 10 条结果
            "sort_by": "relevance", # 默认按相关度排序
            "date_from": "",        # 默认无起始日期
            "date_to": "",          # 默认无结束日期
            "api_key": "",          # 默认无 API Key
        }

    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        """从 PubMed 获取文献内容。

        步骤:
        1. ESearch:根据查询条件搜索文献,获取 PMID 列表
        2. EFetch:根据 PMID 列表分批获取文献详情(XML 格式)
        3. 解析 XML,提取标题、摘要、作者、期刊等信息

        Args:
            config: 配置字典

        Yields:
            SourceDocument 对象,每篇文献一个
        """
        query = config.get("query", "").strip()              # 搜索关键词
        max_results = int(config.get("max_results", 10))      # 最大结果数
        sort_by = config.get("sort_by", "relevance")          # 排序方式
        date_from = config.get("date_from", "")               # 起始日期
        date_to = config.get("date_to", "")                   # 结束日期
        api_key = config.get("api_key", "")                   # API Key(可选)

        # 构建日期筛选条件(PubMed 日期字段: Date - Publication)
        date_filter = ""
        if date_from and date_to:
            # 同时有起止日期
            date_filter = f" AND ({date_from}[Date - Publication] : {date_to}[Date - Publication])"
        elif date_from:
            # 仅有起始日期(从 start 到 3000 年)
            date_filter = f" AND {date_from}[Date - Publication] : 3000[Date - Publication]"
        elif date_to:
            # 仅有结束日期(从 1800 年到 end)
            date_filter = f" AND 1800[Date - Publication] : {date_to}[Date - Publication]"

        full_query = f"({query}){date_filter}"  # 组合完整查询字符串

        # NCBI 排序参数映射
        sort_map = {
            "relevance": "relevance",  # 按相关度排序
            "date_desc": "pub_date",   # 按出版日期降序
            "date_asc": "pub_date",    # 按出版日期升序
        }
        ncbi_sort = sort_map.get(sort_by, "relevance")  # 获取 NCBI 排序参数

        # 第 1 步: ESearch - 搜索文献获取 PMID 列表
        await self._rate_limit(api_key)  # 遵守频率限制
        search_params = {
            "db": "pubmed",                    # 数据库:PubMed
            "term": full_query,                # 检索式
            "retmax": str(max_results),        # 最大返回数
            "retmode": "json",                 # 返回格式:JSON
            "sort": ncbi_sort,                 # 排序方式
            "retstart": "0",                   # 起始偏移(分页用)
        }
        if api_key:
            search_params["api_key"] = api_key  # 附带 API Key

        resp = await self._request_with_retry("GET", PUBMED_ESEARCH, params=search_params)
        search_data = resp.json()  # 解析 JSON 响应

        id_list = search_data.get("esearchresult", {}).get("idlist", [])  # 提取 PMID 列表
        if not id_list:
            return  # 无搜索结果则直接返回

        # 第 2 步: EFetch - 分批获取文献详情(每批 10 篇,避免频率限制)
        batch_size = 10
        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]  # 取一批 PMID
            ids_str = ",".join(batch)  # 用逗号连接

            await self._rate_limit(api_key)  # 遵守频率限制
            fetch_params = {
                "db": "pubmed",         # 数据库:PubMed
                "id": ids_str,          # PMID 列表
                "retmode": "xml",       # 返回格式:XML(包含详细字段)
                "rettype": "abstract",  # 返回内容类型:摘要
            }
            if api_key:
                fetch_params["api_key"] = api_key

            resp = await self._request_with_retry("GET", PUBMED_EFETCH, params=fetch_params)
            xml_data = resp.text  # 获取 XML 响应文本

            try:
                root = ET.fromstring(xml_data)  # 解析 XML
            except ET.ParseError:
                continue  # XML 解析失败则跳过该批

            # 遍历每篇文献
            for article in root.iter("PubmedArticle"):
                medline = article.find(".//MedlineCitation")  # 查找 MedlineCitation 节点
                if medline is None:
                    continue

                article_data = medline.find("Article")  # 查找 Article 节点
                if article_data is None:
                    continue

                # 提取标题
                title_el = article_data.find("ArticleTitle")
                title = "".join(title_el.itertext()) if title_el is not None else "Untitled"
                if title and title.startswith("["):
                    title = title.strip("[]")  # 去除中括号

                # 提取摘要
                abstract_el = article_data.find("Abstract")
                content_parts = []  # 存储摘要片段
                if abstract_el is not None:
                    for at in abstract_el.iter("AbstractText"):
                        label = at.get("Label", "")  # 子段标签(如 BACKGROUND, METHODS)
                        text = "".join(at.itertext()).strip()
                        if label:
                            content_parts.append(f"{label}: {text}")  # 带标签的段落
                        else:
                            content_parts.append(text)  # 无标签段落
                content = "\n\n".join(content_parts) if content_parts else ""  # 合并摘要
                if not content:
                    continue  # 无摘要则跳过

                # 提取作者列表
                author_list = article_data.find("AuthorList")
                authors = []  # 存储作者字符串
                if author_list is not None:
                    for author in author_list.findall("Author"):
                        last = author.find("LastName")    # 姓
                        fore = author.find("ForeName")    # 名
                        if last is not None and fore is not None:
                            authors.append(f"{fore.text} {last.text}")  # 规范格式:名 姓
                        elif last is not None:
                            authors.append(last.text)  # 仅有姓

                # 提取 PMID(PubMed 唯一标识符)
                pmid_el = medline.find("PMID")
                pmid = pmid_el.text if pmid_el is not None else ""

                # 提取出版日期
                pub_date = None
                # 优先使用 PubMedPubDate[@PubStatus='pubmed']
                article_date = article_data.find(".//PubMedPubDate[@PubStatus='pubmed']")
                if article_date is None:
                    # 备用:使用 entrez 状态
                    article_date = article_data.find(".//PubMedPubDate[@PubStatus='entrez']")
                if article_date is not None:
                    year = article_date.find("Year")
                    month = article_date.find("Month")
                    day = article_date.find("Day")
                    try:
                        y = int(year.text) if year is not None else 1970
                        m = int(month.text) if month is not None else 1
                        d = int(day.text) if day is not None else 1
                        pub_date = datetime(y, m, d, tzinfo=timezone.utc)  # 构造 UTC 时间
                    except (ValueError, TypeError):
                        pass  # 解析失败则保持 None

                # 提取期刊名称
                journal_el = article_data.find("Journal/Title")
                journal = "".join(journal_el.itertext()) if journal_el is not None else ""

                # 提取 DOI
                doi_el = article.find(".//ArticleId[@IdType='doi']")
                doi = doi_el.text if doi_el is not None else ""

                # 构建文章 URL
                article_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""

                # 组织元数据
                metadata = {
                    "pmid": pmid,                    # PubMed ID
                    "doi": doi,                      # 数字对象标识符
                    "journal": journal,               # 期刊名称
                    "authors": authors[:5],           # 仅保留前 5 位作者
                    "author_count": len(authors),     # 作者总数
                }

                yield SourceDocument(
                    title=title.strip(),                  # 文献标题
                    content=content.strip(),              # 摘要内容
                    source_url=article_url,               # 文献页面 URL
                    source_id_field=pmid,                 # PMID 作为唯一标识
                    authors=authors,                      # 作者列表
                    publication_date=pub_date,            # 出版日期
                    metadata=metadata,                    # 附加元数据
                )


# 在模块加载时注册适配器,使其可被适配器工厂发现
register_adapter(PubMedAdapter)
