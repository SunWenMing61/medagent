"""默沙东诊疗手册(MSD Manuals)适配器,使用网页爬取方式获取内容。

爬取中文专业版 https://www.msdmanuals.cn/professional/
内容组织方式为树形结构: 章节(Section) -> 章(Chapter) -> 主题(Topic)
"""

import re   # 正则表达式,用于文本清洗
import time  # 时间工具,用于请求间隔控制(频率限制)
from typing import AsyncGenerator, Optional  # 异步生成器和可选类型

import httpx  # HTTP 客户端库(支持异步)
from bs4 import BeautifulSoup  # HTML 解析库

from app.adapters.base import BaseSourceAdapter, SourceDocument  # 基础适配器和文档类型
from app.adapters import register_adapter  # 适配器注册函数

# 默沙东诊疗手册网站基础 URL
MSD_BASE = "https://www.msdmanuals.cn"
# 专业版首页 URL
MSD_PROFESSIONAL = f"{MSD_BASE}/professional"


class MSDManualAdapter(BaseSourceAdapter):
    """默沙东诊疗手册适配器,通过爬取网页获取医学内容。"""
    source_type = "msd_manual"  # 来源类型标识
    display_name = "默沙东诊疗手册"  # 显示名称

    def __init__(self):
        self._last_request_time = 0.0  # 上次请求时间,用于频率限制

    def _rate_limit(self, delay_ms: int = 1500):
        """请求之间的等待,避免对服务器造成压力。

        Args:
            delay_ms: 两次请求之间的最小间隔(毫秒),默认 1500ms
        """
        min_interval = delay_ms / 1000.0  # 转为秒
        elapsed = time.time() - self._last_request_time  # 计算距上次请求的时间
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)  # 如果时间差小于最小间隔,则等待
        self._last_request_time = time.time()  # 更新上次请求时间

    def validate_config(self, config: dict) -> tuple[bool, Optional[str]]:
        """验证配置:检查 max_topics 和 request_delay_ms 是否在有效范围内。

        Args:
            config: 配置字典

        Returns:
            (is_valid, error_message) 元组
        """
        max_topics = config.get("max_topics", 200)  # 最大主题数
        if not isinstance(max_topics, int) or max_topics < 1 or max_topics > 5000:
            return False, "max_topics 必须在 1-5000 之间"
        delay = config.get("request_delay_ms", 1500)  # 请求间隔(毫秒)
        if delay < 200 or delay > 10000:
            return False, "请求延迟必须在 200-10000ms 之间"
        return True, None

    def get_config_schema(self) -> dict:
        """返回前端渲染配置表单所需的 JSON Schema。

        Returns:
            JSON Schema 字典
        """
        return {
            "type": "object",
            "title": "默沙东诊疗手册配置",
            "properties": {
                "max_topics": {           # 每次同步获取的最大主题数
                    "type": "integer",
                    "title": "最大主题数",
                    "description": "每次同步获取的最大主题数量",
                    "default": 200,
                    "minimum": 1,
                    "maximum": 5000,
                },
                "include_full_text": {     # 是否获取完整正文
                    "type": "boolean",
                    "title": "获取全文",
                    "description": "是否获取完整正文内容（否则只获取引言段落）",
                    "default": True,
                },
                "request_delay_ms": {      # HTTP 请求间隔(毫秒)
                    "type": "integer",
                    "title": "请求间隔 (毫秒)",
                    "description": "每次 HTTP 请求之间的等待时间",
                    "default": 1500,
                    "minimum": 200,
                    "maximum": 10000,
                },
                "version": {               # 版本选择:专业版或大众版
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
        """返回默认配置值。"""
        return {
            "max_topics": 200,         # 默认最多获取 200 个主题
            "include_full_text": True, # 默认获取全文
            "request_delay_ms": 1500,  # 默认请求间隔 1500ms
            "version": "professional", # 默认专业版
        }

    async def _fetch_soup(self, client: httpx.AsyncClient, url: str, delay_ms: int) -> Optional[BeautifulSoup]:
        """获取 URL 内容并返回 BeautifulSoup 解析对象,附带频率限制。

        Args:
            client: httpx 异步客户端
            url: 要抓取的页面 URL
            delay_ms: 请求间隔(毫秒)

        Returns:
            BeautifulSoup 对象,失败时返回 None
        """
        self._rate_limit(delay_ms)  # 遵守频率限制
        try:
            resp = await client.get(url, follow_redirects=True, timeout=30)  # 发送 GET 请求,跟踪重定向
            resp.raise_for_status()  # 检查响应状态
            return BeautifulSoup(resp.text, "html.parser")  # 解析 HTML
        except Exception:
            return None  # 失败返回 None

    async def fetch_content(
        self, config: dict,
    ) -> AsyncGenerator[SourceDocument, None]:
        """从默沙东诊疗手册获取内容。

        步骤:
        1. 获取首页以发现章节链接
        2. 遍历章节获取主题链接
        3. 遍历主题解析内容

        Args:
            config: 配置字典

        Yields:
            SourceDocument 对象
        """
        max_topics = int(config.get("max_topics", 200))  # 最大主题数
        include_full_text = config.get("include_full_text", True)  # 是否获取全文
        delay_ms = int(config.get("request_delay_ms", 1500))  # 请求间隔
        version = config.get("version", "professional")  # 版本

        base_url = f"{MSD_BASE}/{version}" if version == "professional" else f"{MSD_BASE}/home"

        topic_count = 0  # 已获取的主题计数
        async with httpx.AsyncClient(timeout=30) as client:
            # 第 1 步:获取首页以发现章节链接
            soup = await self._fetch_soup(client, base_url, delay_ms)
            if soup is None:
                return  # 首页获取失败则直接返回

            # 从目录或侧边栏发现章节链接
            section_urls = self._extract_section_urls(soup, base_url)
            if not section_urls:
                # 备用方法:尝试常见链接选择器
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if f"/{version}/" in href and not href.startswith("http"):
                        href = f"{MSD_BASE}{href}"
                    if href not in section_urls:
                        section_urls.append(href)

            # 遍历每个章节
            for section_url in section_urls:
                if topic_count >= max_topics:
                    break  # 达到最大数量则停止

                soup = await self._fetch_soup(client, section_url, delay_ms)
                if soup is None:
                    continue

                # 从章节页面提取主题链接
                topic_urls = self._extract_topic_urls(soup, base_url)
                for topic_url in topic_urls:
                    if topic_count >= max_topics:
                        break  # 达到最大数量则停止

                    soup = await self._fetch_soup(client, topic_url, delay_ms)
                    if soup is None:
                        continue

                    doc = self._parse_topic(soup, topic_url, include_full_text)  # 解析主题页面
                    if doc is not None:
                        topic_count += 1  # 主题计数加一
                        yield doc  # 产出解析后的文档

    def _extract_section_urls(self, soup: BeautifulSoup, base_url: str) -> list:
        """从导航中发现章节/章的 URL 列表。

        Args:
            soup: 首页的 BeautifulSoup 对象
            base_url: 基础 URL,用于拼接相对链接

        Returns:
            章节 URL 列表(已去重)
        """
        urls = []   # 存储发现的 URL
        seen = set()  # 用于去重

        # 尝试默沙东诊疗手册可能使用的各种导航选择器
        selectors = [
            "nav a[href]",                # 导航菜单链接
            ".toc a[href]",               # 目录链接
            ".nav-toc a[href]",           # 导航目录链接
            ".sidebar-nav a[href]",       # 侧边栏导航链接
            "[data-testid='toc'] a[href]",  # 测试 ID 标记的目录
            ".navigation a[href]",        # 通用导航链接
        ]

        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href", "")
                if href.startswith("/"):
                    href = f"{MSD_BASE}{href}"  # 相对路径转为绝对路径
                if base_url in href and href not in seen:
                    seen.add(href)  # 加入去重集合
                    urls.append(href)  # 加入结果列表

        return urls

    def _extract_topic_urls(self, soup: BeautifulSoup, base_url: str) -> list:
        """从章节页面提取主题(文章)页面的 URL 列表。

        Args:
            soup: 章节页面的 BeautifulSoup 对象
            base_url: 基础 URL,用于拼接相对链接

        Returns:
            主题 URL 列表(已去重)
        """
        urls = []   # 存储发现的 URL
        seen = set()  # 用于去重

        # 各种可能的主题列表选择器
        selectors = [
            ".topic-list a[href]",         # 主题列表链接
            ".article-list a[href]",       # 文章列表链接
            ".content-list a[href]",       # 内容列表链接
            "main a[href]",                # 主体内容链接
            "[data-testid='topic-list'] a[href]",  # 测试 ID 标记的主题列表
            "ul li a[href]",               # 列表项链接
        ]

        for selector in selectors:
            for link in soup.select(selector):
                href = link.get("href", "")
                if not href or "#" in href:
                    continue  # 跳过空链接和锚点链接
                if href.startswith("/"):
                    href = f"{MSD_BASE}{href}"  # 相对路径转为绝对路径
                if base_url in href and href not in seen:
                    seen.add(href)  # 去重
                    urls.append(href)

        return urls

    def _parse_topic(
        self, soup: BeautifulSoup, url: str, include_full_text: bool,
    ) -> Optional[SourceDocument]:
        """解析单个主题页面为 SourceDocument 对象。

        Args:
            soup: 主题页面的 BeautifulSoup 对象
            url: 当前主题的 URL
            include_full_text: 是否包含完整正文,否则仅取前 500 字符

        Returns:
            SourceDocument 对象,解析失败时返回 None
        """
        # 提取标题
        title_el = (
            soup.find("h1")                              # <h1> 标签
            or soup.find("[data-testid='page-title']")    # 测试 ID 标记
            or soup.find("title")                         # <title> 标签
        )
        if title_el is None:
            return None  # 无标题则返回 None
        title = title_el.get_text(strip=True)  # 获取纯文本标题

        # 从标题中移除网站名称后缀
        for suffix in [" - MSD诊疗手册专业版", " - 默沙东诊疗手册", " | MSD Manuals"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)]  # 去除后缀

        # 提取内容
        content_parts = []  # 存储内容片段

        # 尝试各种主内容区域的选择器
        main_selectors = [
            "main",                    # <main> 标签
            "[role='main']",           # role="main" 属性
            ".content-body",           # 内容主体 class
            ".article-content",        # 文章内容 class
            ".topic-content",          # 主题内容 class
            "#content",                # content ID
            "article",                 # <article> 标签
        ]

        content_el = None
        for sel in main_selectors:
            el = soup.select_one(sel)
            if el:
                content_el = el  # 找到第一个匹配的元素
                break

        if content_el is None:
            # 最后备选:从 <body> 提取
            content_el = soup.find("body")

        if content_el is None:
            return None  # 无可解析内容

        # 删除不需要的元素(脚本、样式、导航、页眉、页脚、侧边栏)
        for tag in content_el.find_all(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()  # 从 DOM 树中移除

        # 提取标题和段落文本
        for elem in content_el.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li"]):
            text = elem.get_text(strip=True)
            if text and len(text) > 5:  # 过滤太短的文本片段
                if elem.name.startswith("h"):
                    content_parts.append(f"\n## {text}\n")  # 标题格式化为 Markdown 二级标题
                elif elem.name == "li":
                    content_parts.append(f"- {text}")        # 列表项添加 Markdown 列表符号
                else:
                    content_parts.append(text)               # 普通段落

        full_content = "\n\n".join(content_parts)  # 用双换行连接所有内容片段

        if not full_content.strip():
            return None  # 无有效内容则返回 None

        # 清洗多余空行:将 3 个以上连续换行替换为 2 个
        full_content = re.sub(r"\n{3,}", "\n\n", full_content).strip()

        # 如果不是全文模式,只取前 500 字符作为摘要
        if not include_full_text:
            full_content = full_content[:500]

        # 获取面包屑导航,用于上下文
        breadcrumbs = []
        for crumb in soup.select("[class*='breadcrumb'] a"):
            text = crumb.get_text(strip=True)
            if text:
                breadcrumbs.append(text)

        return SourceDocument(
            title=title,                     # 主题标题
            content=full_content,             # 正文内容
            source_url=url,                   # 来源 URL
            source_id_field=url,              # 以 URL 作为唯一标识
            metadata={
                "breadcrumbs": breadcrumbs,   # 面包屑导航
                "version": "professional",    # 版本信息
                "section": breadcrumbs[0] if breadcrumbs else "",  # 所属章节
            },
        )


# 在模块加载时注册适配器,使其可被适配器工厂发现
register_adapter(MSDManualAdapter)
