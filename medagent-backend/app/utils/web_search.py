"""网络搜索工具,用于执行网络搜索并格式化搜索结果供 LLM 使用。"""

import logging  # 日志记录
from typing import List, Optional  # 列表和可选类型提示

logger = logging.getLogger(__name__)  # 获取当前模块的日志记录器

SEARCH_RESULT_COUNT = 5  # 每次搜索返回的结果数量


def search_web(query: str, api_key: Optional[str] = None, api_base: str = "https://google.serper.dev") -> List[dict]:
    """通过兼容 Serper.dev 的 API 执行网络搜索并返回结果摘要。

    每个结果字典包含 title、snippet、link 三个键。
    如果失败或未配置 API 密钥则返回空列表。

    Args:
        query: 搜索关键词
        api_key: Serper.dev API 密钥,为 None 时直接返回空列表
        api_base: API 的基础 URL,默认使用 Serper.dev

    Returns:
        搜索结果字典列表,每个字典包含 title、snippet、link
    """
    if not api_key:
        logger.warning("SEARCH_API_KEY not configured — web search unavailable")  # 未配置密钥时记录警告
        return []  # 无 API 密钥则直接返回空列表

    import httpx  # 内部导入 httpx 用于发送 HTTP 请求

    try:
        # 创建同步 HTTP 客户端,设置 15 秒超时
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{api_base}/search",  # 拼接搜索 API 地址
                headers={
                    "X-API-KEY": api_key,            # Serper.dev 认证头
                    "Content-Type": "application/json",
                },
                json={"q": query, "num": SEARCH_RESULT_COUNT},  # 请求体:查询词和结果数量
            )
            response.raise_for_status()  # 检查响应状态码
            data = response.json()  # 解析 JSON 响应

            results = []  # 存储格式化后的搜索结果
            # 遍历响应中的 organic(自然搜索结果)列表
            for item in data.get("organic", []):
                results.append({
                    "title": item.get("title", ""),    # 结果标题
                    "snippet": item.get("snippet", ""), # 结果摘要
                    "link": item.get("link", ""),       # 结果链接
                })
            return results
    except Exception as e:
        logger.error("Web search failed: %s", e)  # 记录错误日志
        return []  # 出错时返回空列表


def format_search_results(results: List[dict]) -> str:
    """将搜索结果格式化为 LLM 提示上下文可用的字符串。

    Args:
        results: search_web 返回的搜索结果字典列表

    Returns:
        格式化后的文本字符串,包含标题、摘要和来源链接
    """
    if not results:
        return ""  # 无结果则返回空字符串

    parts = ["🌐 **来自网络搜索结果:**"]  # 标题头
    for i, r in enumerate(results, 1):  # 从 1 开始编号
        title = r.get("title", "")     # 结果标题
        snippet = r.get("snippet", "")  # 结果摘要
        link = r.get("link", "")        # 结果链接
        parts.append(f"**{i}. {title}**")  # 添加编号和标题
        if snippet:
            parts.append(f"   {snippet}")  # 添加摘要(缩进)
        if link:
            parts.append(f"   来源: {link}")  # 添加来源链接
    return "\n\n".join(parts)  # 用双换行连接各部分
