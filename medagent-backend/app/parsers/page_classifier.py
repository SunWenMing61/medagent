"""Deterministic page classification from layout, images and text quality."""

from __future__ import annotations

import re
from collections.abc import Iterable

import fitz

from app.core.config import settings
from app.parsers.models import PageClassification, TextBlock


_READABLE = re.compile(r"[\w\u4e00-\u9fff\u0370-\u03ff]", re.UNICODE)
_REPLACEMENT = re.compile(r"[\ufffd\x00-\x08\x0b\x0c\x0e-\x1f]")


def garbled_ratio(text: str) -> float:
    if not text:
        return 0.0
    suspicious = len(_REPLACEMENT.findall(text))
    non_space = [char for char in text if not char.isspace()]
    unreadable = sum(not _READABLE.match(char) and not char.isprintable() for char in non_space)
    return min(1.0, (suspicious + unreadable) / max(len(non_space), 1))


def _image_coverage(page: fitz.Page) -> tuple[int, float]:
    page_area = max(float(page.rect.width * page.rect.height), 1.0)
    areas: list[float] = []
    for image in page.get_images(full=True):
        try:
            for rect in page.get_image_rects(image[0]):
                areas.append(max(0.0, float(rect.width * rect.height)))
        except Exception:
            continue
    return len(areas), min(1.0, sum(areas) / page_area)


def _column_count(blocks: Iterable[TextBlock], page_width: float) -> int:
    centers = sorted(
        (block.bbox[0] + block.bbox[2]) / 2
        for block in blocks
        if block.bbox and (block.bbox[2] - block.bbox[0]) < page_width * 0.72
    )
    if len(centers) < 4:
        return 1
    split = max(range(1, len(centers)), key=lambda index: centers[index] - centers[index - 1])
    gap = centers[split] - centers[split - 1]
    return 2 if gap >= page_width * 0.16 and split >= 2 and len(centers) - split >= 2 else 1


def classify_page(page: fitz.Page, blocks: list[TextBlock], table_count: int) -> PageClassification:
    text = "\n".join(block.text for block in blocks if block.kind != "figure")
    chars = len(re.sub(r"\s+", "", text))
    images, image_coverage = _image_coverage(page)
    garbled = garbled_ratio(text)
    columns = _column_count(blocks, float(page.rect.width))
    minimum = max(int(settings.OCR_MIN_NATIVE_TEXT_CHARS), 0)

    if chars == 0 and images == 0:
        page_type, mode, reason = "empty", "ocr_only", "No text or image region was found; one OCR attempt can confirm a blank page."
    elif garbled >= 0.2 and chars >= minimum:
        page_type, mode, reason = "garbled", "hybrid", "Embedded text has a high invalid-character ratio."
    elif table_count > 0 and (table_count >= 2 or chars >= minimum):
        page_type, mode, reason = "table_heavy", "embedded_only", "One or more structured tables were detected."
    elif chars < minimum and image_coverage >= 0.35:
        page_type, mode, reason = "scanned", "ocr_only", "Sparse text layer and a page-sized image indicate a scan."
    elif images and (image_coverage >= 0.12 or chars < minimum):
        page_type, mode, reason = "hybrid", "hybrid", "Readable text and image regions both require preservation."
    elif columns > 1:
        page_type, mode, reason = "complex_layout", "embedded_only", "Multiple stable text columns were detected."
    elif chars < minimum:
        page_type, mode, reason = "scanned", "ocr_only", "The embedded text layer is below the configured threshold."
    else:
        page_type, mode, reason = "embedded_text", "embedded_only", "Readable embedded text is sufficient."

    return PageClassification(
        page_num=page.number + 1,
        page_type=page_type,  # type: ignore[arg-type]
        embedded_char_count=chars,
        image_count=images,
        image_coverage_ratio=round(image_coverage, 4),
        text_block_count=sum(block.kind != "figure" for block in blocks),
        table_count=table_count,
        garbled_ratio=round(garbled, 4),
        requires_ocr=mode in {"ocr_only", "hybrid"},
        extraction_mode=mode,  # type: ignore[arg-type]
        reason=reason,
    )
