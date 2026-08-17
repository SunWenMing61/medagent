"""文本清洗与块质量过滤工具，用于向量化前提升文本质量。"""

import re
import unicodedata
import html

# ── 零宽字符集合 ────────────────────────────────────────────────────────────────
# 这些 Unicode 字符不占据可视宽度，会干扰文本处理且浪费嵌入维度
ZERO_WIDTH_CHARS = re.compile(
    "[​‌‍⁠﻿­᠎‎‏‪‫‬‭‮⁡⁢⁣⁤]"
)

# ── 全角字符范围 ────────────────────────────────────────────────────────────────
# 全角拉丁字母、数字、常见标点（保留中文全角标点如 。，、；：？！）
FULLWIDTH_MAP = {
    ord("０"): "0", ord("１"): "1", ord("２"): "2", ord("３"): "3", ord("４"): "4",
    ord("５"): "5", ord("６"): "6", ord("７"): "7", ord("８"): "8", ord("９"): "9",
    ord("Ａ"): "A", ord("Ｂ"): "B", ord("Ｃ"): "C", ord("Ｄ"): "D", ord("Ｅ"): "E",
    ord("Ｆ"): "F", ord("Ｇ"): "G", ord("Ｈ"): "H", ord("Ｉ"): "I", ord("Ｊ"): "J",
    ord("Ｋ"): "K", ord("Ｌ"): "L", ord("Ｍ"): "M", ord("Ｎ"): "N", ord("Ｏ"): "O",
    ord("Ｐ"): "P", ord("Ｑ"): "Q", ord("Ｒ"): "R", ord("Ｓ"): "S", ord("Ｔ"): "T",
    ord("Ｕ"): "U", ord("Ｖ"): "V", ord("Ｗ"): "W", ord("Ｘ"): "X", ord("Ｙ"): "Y",
    ord("Ｚ"): "Z",
    ord("ａ"): "a", ord("ｂ"): "b", ord("ｃ"): "c", ord("ｄ"): "d", ord("ｅ"): "e",
    ord("ｆ"): "f", ord("ｇ"): "g", ord("ｈ"): "h", ord("ｉ"): "i", ord("ｊ"): "j",
    ord("ｋ"): "k", ord("ｌ"): "l", ord("ｍ"): "m", ord("ｎ"): "n", ord("ｏ"): "o",
    ord("ｐ"): "p", ord("ｑ"): "q", ord("ｒ"): "r", ord("ｓ"): "s", ord("ｔ"): "t",
    ord("ｕ"): "u", ord("ｖ"): "v", ord("ｗ"): "w", ord("ｘ"): "x", ord("ｙ"): "y",
    ord("ｚ"): "z",
    # 全角括号与符号 → 半角（保留用于 Markdown 格式的场景）
    ord("（"): "(", ord("）"): ")", ord("［"): "[", ord("］"): "]",
    ord("｛"): "{", ord("｝"): "}", ord("＜"): "<", ord("＞"): ">",
    ord("＠"): "@", ord("＃"): "#", ord("＄"): "$", ord("％"): "%",
    ord("＾"): "^", ord("＆"): "&", ord("＊"): "*",
    ord("＋"): "+", ord("＝"): "=", ord("～"): "~",
    ord("　"): " ",   # 全角空格
}

# ── 重复页眉/页脚模式（医疗文档常见） ─────────────────────────────────────
# 简单的连续重复行检测（相同行出现 3 次以上）
REPEATED_PATTERN = re.compile(r"^(.{2,80})\n(?:\1\n){2,}", re.MULTILINE)

# ── URL 检测 ──────────────────────────────────────────────────────────────────────
URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

# ── 纯标点/数字/空白检测 ─────────────────────────────────────────────────────────
# 用于 filter_chunk 的快速判别
PUNCT_DIGIT_SPACE = re.compile(r"^[\s\d\W]+$")


def clean_text(text: str, remove_urls: bool = False) -> str:
    """清洗文本，去除噪声并规范化格式。

    执行顺序：
    1. Unicode 正规化（NFC） + 零宽字符移除
    2. HTML 实体解码（&amp; → & 等）
    3. 全角拉丁字母/数字/符号 → 半角（保留中文标点）
    4. URL 可选移除
    5. 重复页眉/页脚行清理
    6. 空白规范化（多空格→单空格，段落间最多保留 2 换行）

    Args:
        text: 原始文本
        remove_urls: 是否移除 URL 链接

    Returns:
        清洗后的文本
    """
    if not text:
        return ""

    # 1. Unicode NFC 标准化 + 零宽字符移除
    text = unicodedata.normalize("NFC", text)
    text = ZERO_WIDTH_CHARS.sub("", text)

    # 2. HTML 实体解码
    text = html.unescape(text)

    # 3. 全角拉丁字母/数字/符号 → 半角（保留中文全角标点）
    text = text.translate(FULLWIDTH_MAP)

    # 4. 可选移除 URL
    if remove_urls:
        text = URL_PATTERN.sub("", text)

    # 5. 清理重复行（连续重复 3 次以上的页眉页脚）
    text = REPEATED_PATTERN.sub(r"\1\n", text)

    # 6. 空白规范化
    # 将各种换行风格统一为 \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 将 Tab 替换为单个空格
    text = text.replace("\t", " ")
    # 多空格 → 单空格（保留缩进和列表格式）
    text = re.sub(r" {2,}", " ", text)
    # 将 3 个以上连续换行压缩为 2 个（保留段落分隔）
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def filter_chunk(
    chunk: str,
    min_chars: int = 15,
    max_chars: int = 2000,
) -> str | None:
    """验证文本块的质量，只保留有意义的块。

    过滤规则：
    - 长度不足 min_chars → 丢弃
    - 超过 max_chars → 丢弃（应已在分块阶段处理）
    - 仅含标点/数字/空白 → 丢弃
    - 仅含单字符重复（如 "------"） → 丢弃

    Args:
        chunk: 待验证的文本块
        min_chars: 最小字符数阈值
        max_chars: 最大字符数阈值

    Returns:
        验证通过的文本块，或 None（应丢弃）
    """
    if not chunk:
        return None

    stripped = chunk.strip()
    if not stripped:
        return None

    # 长度检查
    if len(stripped) < min_chars:
        return None
    if len(stripped) > max_chars:
        return None

    # 仅含标点/数字/空白
    if PUNCT_DIGIT_SPACE.match(stripped):
        return None

    # 仅含重复的单个字符（如 "======", "----", "****"）
    if len(set(stripped)) <= 2 and len(stripped) < 30:
        return None

    return stripped


def clean_and_filter_chunks(chunks: list[str], min_chars: int = 15) -> list[str]:
    """对分块结果批量清洗并过滤质量。

    相当于对每个块先 strip，再 filter_chunk。

    Args:
        chunks: 分块结果列表
        min_chars: 最小字符数

    Returns:
        清洗过滤后的块列表
    """
    result = []
    for chunk in chunks:
        valid = filter_chunk(chunk, min_chars=min_chars)
        if valid:
            result.append(valid)
    return result
