from typing import List


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 100) -> List[str]:
    """Split text into chunks with overlap. Uses simple sentence-aware splitting."""
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        if end >= text_len:
            chunks.append(text[start:].strip())
            break

        cutoff = text.rfind("。", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = text.rfind(".", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = text.rfind("\n", start, end)
        if cutoff == -1 or cutoff < start:
            cutoff = end

        chunks.append(text[start:cutoff + 1].strip())
        start = cutoff + 1 - chunk_overlap
        if start < 0:
            start = 0

    return [c for c in chunks if c]
