# 从 typing 模块导入 List 类型,用于函数签名中的列表类型提示
from typing import List


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 100) -> List[str]:
    """将文本分块,块之间有重叠。使用简单的句子感知分割策略。

    Args:
        text: 要分割的原始文本
        chunk_size: 每块的最大字符数,默认 500
        chunk_overlap: 相邻块之间的重叠字符数,默认 100

    Returns:
        文本块字符串列表
    """
    if not text:        # 空文本直接返回空列表
        return []

    chunks = []         # 存储分块结果
    start = 0           # 当前块的起始位置
    text_len = len(text)  # 文本总长度

    while start < text_len:
        end = start + chunk_size  # 当前块的理论结束位置
        if end >= text_len:       # 如果结束位置超出文本长度
            chunks.append(text[start:].strip())  # 取剩余全部文本
            break

        # 优先在中文句号处断开
        cutoff = text.rfind("。", start, end)
        if cutoff == -1 or cutoff < start:
            # 如果没有中文句号,尝试英文句点
            cutoff = text.rfind(".", start, end)
        if cutoff == -1 or cutoff < start:
            # 如果没有句号,尝试在换行符处断开
            cutoff = text.rfind("\n", start, end)
        if cutoff == -1 or cutoff < start:
            # 如果以上分隔符都没有,在 chunk_size 位置强制断开
            cutoff = end

        # 提取从 start 到 cutoff(含)的文本块
        chunks.append(text[start:cutoff + 1].strip())
        # 下一块的起始位置回退 chunk_overlap 字符数,实现重叠
        start = cutoff + 1 - chunk_overlap
        if start < 0:   # 防止起始位置为负数
            start = 0

    # 过滤掉空白块后返回
    return [c for c in chunks if c]
