"""文本分块工具，提供多级分块策略并集成文本清洗。"""

import logging
import re
from typing import List, Optional

# ── LangChain 智能分块依赖 ──────────────────────────────────────────────────────
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    _LANGCHAIN_AVAILABLE = True
except ImportError:
    _LANGCHAIN_AVAILABLE = False

# ── 文本清洗依赖 ────────────────────────────────────────────────────────────────
from app.utils.text_cleaner import clean_text, filter_chunk

logger = logging.getLogger(__name__)


# =============================================================================
#  统一入口
# =============================================================================

def clean_and_split(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    min_chunk_chars: int = 15,
    max_chunk_chars: int = 2000,
    remove_urls: bool = False,
    prefer_smart: bool = True,
) -> List[str]:
    """清洗 + 分块 + 质量过滤一体化入口。

    流水线：
        1. clean_text() —— 去除噪声、规范化格式
        2. split_text_smart() 或 split_text() —— 按语义分块
        3. filter_chunk() —— 丢弃低质量块

    Args:
        text: 原始文本
        chunk_size: 每块最大字符数
        chunk_overlap: 块间重叠字符数
        min_chunk_chars: 块质量过滤——最小字符数
        max_chunk_chars: 块质量过滤——最大字符数
        remove_urls: 是否移除 URL 链接
        prefer_smart: 是否优先使用 LangChain 智能分块

    Returns:
        经过清洗、分块、过滤后的文本块列表
    """
    if not text:
        return []

    # Step 1: 清洗
    cleaned = clean_text(text, remove_urls=remove_urls)
    if not cleaned:
        return []

    # Step 2: 分块
    if prefer_smart and _LANGCHAIN_AVAILABLE:
        raw_chunks = split_text_smart(cleaned, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    else:
        raw_chunks = split_text(cleaned, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    # Step 3: 质量过滤
    result = []
    for c in raw_chunks:
        valid = filter_chunk(c, min_chars=min_chunk_chars, max_chars=max_chunk_chars)
        if valid:
            result.append(valid)

    return result


# =============================================================================
#  快速降级分块（不依赖 LangChain）
# =============================================================================

def _find_sentence_boundary(text: str, pos: int, max_lookback: int = 80) -> int:
    """从 pos 位置向前寻找最近的句子边界（句号/换行）。

    边界优先级：
        - 中文句号（。） > 英文句点（.） > 换行（\\n）
        - 如果在 max_lookback 范围内找不到边界，返回 pos（不强制切）

    Args:
        text: 完整文本
        pos: 参考位置
        max_lookback: 最大前向搜索字符数

    Returns:
        边界位置（含边界字符的下标）
    """
    start = max(0, pos - max_lookback)
    segment = text[start:pos + 1]

    # 从右向左搜索边界点
    for sep in ("。", "\n", ".", "！", "？", "!", "?"):
        idx = segment.rfind(sep)
        if idx != -1:
            return start + idx + 1  # 返回含分隔符的位置

    return pos  # 找不到则返回原位置


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> List[str]:
    """将文本分块，块间有重叠，重叠对齐到句子边界。

    相比修改前的版本，重叠位置从「固定字符偏移」改进为
    「对齐到最近的句子边界」，避免块从句子中间截断。

    Args:
        text: 要分割的原始文本
        chunk_size: 每块的最大字符数
        chunk_overlap: 相邻块之间的重叠字符数

    Returns:
        文本块字符串列表
    """
    if not text:
        return []

    chunks: List[str] = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)

        if end >= text_len:
            chunks.append(text[start:].strip())
            break

        # 优先在中文句号处断开
        cutoff = text.rfind("。", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = text.rfind(".", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = text.rfind("\n", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = text.rfind("！", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = text.rfind("？", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = end  # 无合适分隔符时强制切断

        chunks.append(text[start:cutoff + 1].strip())

        # 计算下一块起始位置：对齐到句子边界
        next_start = cutoff + 1 - chunk_overlap
        if next_start < 0:
            next_start = 0
        else:
            # 对齐到最近的句子边界（避免从句子中间开始）
            aligned = _find_sentence_boundary(text, next_start)
            # 防止回退到当前块的起始位置导致死循环
            if aligned <= start:
                aligned = next_start
            next_start = aligned

        start = next_start

    return [c for c in chunks if c]


# =============================================================================
#  LangChain 智能分块（推荐）
# =============================================================================

def split_text_smart(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
) -> List[str]:
    """使用 LangChain RecursiveCharacterTextSplitter 进行智能分块。

    相比 split_text() 的简单分割，此函数能更好地保留表格结构、
    代码块和列表格式，并按语义优先级（表格/代码块 > 标题 > 段落 > 句子）分割。

    Args:
        text: 要分割的原始文本
        chunk_size: 每块的最大字符数
        chunk_overlap: 块间重叠字符数

    Returns:
        文本块字符串列表
    """
    if not text:
        return []

    if not _LANGCHAIN_AVAILABLE:
        logger.warning("langchain not installed, falling back to basic split_text()")
        return split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    # 自定义分隔符优先级列表（按语义保真度从高到低排列）
    separators = [
        # 1. 表格行：优先保护表格完整性
        "\n|",
        # 2. Markdown 代码块标记
        "```",
        # 3. Markdown 标题
        "\n## ",
        "\n### ",
        "\n#### ",
        "\n# ",
        # 4. 列表项
        "\n- ",
        "\n* ",
        "\n+ ",
        "\n1. ",  # 有序列表
        # 5. 段落边界（双换行）
        "\n\n",
        # 6. 行边界
        "\n",
        # 7. 中文/英文句子标点
        "。",
        "．",
        ". ",
        "！",
        "?",
        "？",
        # 8. 中文短语标点（医疗文本常见）
        "；",
        "：",
        "、",
        ";",
        # 9. 逗号（最后手段）
        "，",
        ",",
        " ",
    ]

    splitter = RecursiveCharacterTextSplitter(
        separators=separators,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=True,
    )

    return [c.strip() for c in splitter.split_text(text) if c.strip()]


# =============================================================================
#  语义分块（按 Markdown 标题保持章节完整性）
# =============================================================================

def split_text_by_semantic(
    text: str,
    max_chunk_size: int = 1000,
) -> List[str]:
    """按语义边界进行文本分割，优先保证章节完整性。

    分割策略优先级：
    1. Markdown 标题（章节级别）
    2. 段落（双换行）
    3. 长段落按句子分割（句号/问号/感叹号）

    此函数不产生重叠，适用于需要保持语义完整性的场景。

    Args:
        text: 要分割的原始文本
        max_chunk_size: 每块的最大字符数

    Returns:
        语义块字符串列表
    """
    if not text:
        return []

    lines = text.split("\n")
    sections: List[str] = []
    current_section = ""

    for line in lines:
        if re.match(r"^#{1,6}\s+", line):
            if current_section.strip():
                sections.append(current_section.strip())
            current_section = line
        else:
            current_section = current_section + "\n" + line if current_section else line

    if current_section.strip():
        sections.append(current_section.strip())

    if len(sections) == 1 and not re.search(r"^#{1,6}\s+", text, re.MULTILINE):
        sections = [text.strip()]

    result_chunks: List[str] = []

    for section in sections:
        if len(section) <= max_chunk_size:
            result_chunks.append(section)
            continue

        sub_paragraphs = [p.strip() for p in section.split("\n\n") if p.strip()]

        buffer = ""
        for para in sub_paragraphs:
            if len(para) > max_chunk_size:
                if buffer:
                    result_chunks.append(buffer)
                    buffer = ""

                sentences = re.split(
                    r"(?<=[。．！？!?\n])\s*",
                    para,
                )
                sent_buffer = ""
                for sent in sentences:
                    if not sent.strip():
                        continue
                    if len(sent_buffer) + len(sent) > max_chunk_size:
                        if sent_buffer:
                            result_chunks.append(sent_buffer.strip())
                        sent_buffer = sent
                    else:
                        sent_buffer += sent
                if sent_buffer.strip():
                    result_chunks.append(sent_buffer.strip())
                continue

            if not buffer:
                buffer = para
            elif len(buffer) + len(para) + 2 <= max_chunk_size:
                buffer += "\n\n" + para
            else:
                result_chunks.append(buffer)
                buffer = para

        if buffer:
            result_chunks.append(buffer)

    return [c for c in result_chunks if c.strip()]
