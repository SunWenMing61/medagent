"""Traceable medical-text cleaning with conservative structure recovery."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import Counter
from dataclasses import asdict

from app.core.config import settings
from app.parsers.models import (
    CleaningAction, DocumentQualityReport, ParsedDocument, ParsedTable, SectionNode, TextBlock,
)
from app.parsers.page_classifier import garbled_ratio


_MEDICAL_SYMBOLS = ("mg/mL", "μg", "mmHg", "SpO₂", "eGFR", "β", "≤", "≥", "±", "10⁹/L", "Na⁺", "K⁺")
_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_LIST = re.compile(r"^(?:[-•●▪◦]|\d+[.)]|[一二三四五六七八九十]+[、.]|[（(][一二三四五六七八九十\d]+[）)])\s*")
_HEADING = re.compile(
    r"^(?:第[一二三四五六七八九十百\d]+[章节]|\d+(?:\.\d+){0,3}[、.\s]|[一二三四五六七八九十]+、|"
    r"[（(][一二三四五六七八九十\d]+[）)]|【(?:适应证|禁忌证|用法用量|注意事项|相互作用)】|摘要|关键词|参考文献|References)"
)
_PAGE_NUMBER = re.compile(r"^(?:-\s*)?\d+(?:\s*-)?$|^第\s*\d+\s*页$|^Page\s+\d+(?:\s+of\s+\d+)?$", re.I)
_WATERMARK = re.compile(r"^(?:CONFIDENTIAL|DRAFT|SAMPLE|COPY|机密|草稿|仅供内部使用)$", re.I)
_COMPOUNDS = {"dose-dependent", "double-blind", "case-control", "follow-up", "long-term", "short-term"}


def _table_markdown(headers: list[str], rows: list[list[str]]) -> str:
    width = max(len(headers), max((len(row) for row in rows), default=0))
    if width == 0:
        return ""
    normalized_headers = (headers + [f"Column {index + 1}" for index in range(len(headers), width)])[:width]
    normalized_rows = [(row + [""] * width)[:width] for row in rows]
    lines = [
        "| " + " | ".join(normalized_headers) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in normalized_rows)
    return "\n".join(lines)


def _merge_cross_page_tables(document: ParsedDocument) -> None:
    """Join consecutive table fragments only when their normalized schemas match."""
    previous: ParsedTable | None = None
    for page in document.pages:
        retained: list[ParsedTable | list[list[str]]] = []
        for table in page.tables:
            if not isinstance(table, ParsedTable):
                retained.append(table)
                previous = None
                continue
            normalized_headers = [re.sub(r"\s+", " ", value).strip().lower() for value in table.headers]
            previous_headers = (
                [re.sub(r"\s+", " ", value).strip().lower() for value in previous.headers]
                if previous else []
            )
            can_merge = bool(
                previous
                and previous.page_end + 1 == table.page_start
                and normalized_headers
                and normalized_headers == previous_headers
                and all(len(row) == len(table.headers) for row in table.rows)
            )
            if can_merge and previous is not None:
                continuation_rows = list(table.rows)
                if continuation_rows and [cell.strip().lower() for cell in continuation_rows[0]] == normalized_headers:
                    continuation_rows = continuation_rows[1:]
                previous.rows.extend(continuation_rows)
                previous.page_end = table.page_end
                previous.footnotes.extend(item for item in table.footnotes if item not in previous.footnotes)
                previous.confidence = round(min(previous.confidence, table.confidence), 4)
                previous.markdown = _table_markdown(previous.headers, previous.rows)
                document.cleaning_actions.append(CleaningAction(
                    action_type="merge_cross_page_table",
                    original_text=table.markdown,
                    cleaned_text=previous.markdown,
                    rule="consecutive_pages_with_identical_normalized_headers",
                    confidence=previous.confidence,
                    page_num=page.page_number,
                    block_id=table.table_id,
                ))
                continue
            retained.append(table)
            previous = table
        page.tables = retained


def _record(document: ParsedDocument, block: TextBlock, page_num: int, action: str, original: str, cleaned: str, rule: str, confidence: float) -> None:
    document.cleaning_actions.append(CleaningAction(
        action_type=action,
        original_text=original,
        cleaned_text=cleaned,
        rule=rule,
        confidence=confidence,
        page_num=page_num,
        block_id=block.block_id or f"p{page_num}_unknown",
    ))


def normalize_medical_unicode(text: str) -> str:
    placeholders: dict[str, str] = {}
    protected = text
    for index, symbol in enumerate(_MEDICAL_SYMBOLS):
        key = f"__MEDSYM_{index}__"
        if symbol in protected:
            placeholders[key] = symbol
            protected = protected.replace(symbol, key)
    normalized = unicodedata.normalize("NFKC", protected)
    for key, symbol in placeholders.items():
        normalized = normalized.replace(key, symbol)
    return _ZERO_WIDTH.sub("", normalized.replace("\u00a0", " ").replace("\u3000", " ").replace("\x00", ""))


def _repair_hyphenation(text: str) -> tuple[str, int]:
    repaired = 0

    def replace(match: re.Match) -> str:
        nonlocal repaired
        left, right = match.group(1), match.group(2)
        joined = f"{left}-{right}"
        repaired += 1
        return joined if joined.lower() in _COMPOUNDS else left + right

    return re.sub(r"\b([A-Za-z]{2,})-\s*\n\s*([a-z][A-Za-z]*)\b", replace, text), repaired


def _repair_ocr_units(text: str) -> tuple[str, int]:
    repairs = 0
    patterns = (
        (re.compile(r"(?<![A-Za-z0-9])O(?=\.\d+\s*(?:mg|g|mL|μg)\b)"), "0"),
        (re.compile(r"(?<![A-Za-z0-9])l(?=0\s*(?:mg|g|mL|μg)\b)"), "1"),
        (re.compile(r"\bu\s+g\b", re.I), "μg"),
    )
    for pattern, replacement in patterns:
        text, count = pattern.subn(replacement, text)
        repairs += count
    return text, repairs


def _merge_visual_lines(text: str, kind: str) -> tuple[str, int]:
    if kind in {"title", "heading", "list", "table", "caption", "footnote", "reference"}:
        return text, 0
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return "\n".join(lines), 0
    output = lines[0]
    merged = 0
    for next_line in lines[1:]:
        previous = output.rstrip()
        should_merge = (
            not re.search(r"[。！？!?；;：:]$", previous)
            and not _LIST.match(next_line)
            and not _HEADING.match(next_line)
        )
        if should_merge:
            separator = "" if re.search(r"[\u4e00-\u9fff]$", previous) and re.match(r"^[\u4e00-\u9fff]", next_line) else " "
            output = previous + separator + next_line
            merged += 1
        else:
            output += "\n" + next_line
    return output, merged


def _clean_block(document: ParsedDocument, page_num: int, block: TextBlock) -> tuple[int, int]:
    original = block.text
    value = normalize_medical_unicode(original).replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value, hyphens = _repair_hyphenation(value)
    if hyphens:
        _record(document, block, page_num, "repair_hyphenation", original, value, "line_end_hyphen_lowercase_continuation", 0.92)
    numeric_repairs = 0
    if block.extraction_method == "ocr" or (block.confidence is not None and block.confidence < 0.9):
        before = value
        value, numeric_repairs = _repair_ocr_units(value)
        if numeric_repairs:
            _record(document, block, page_num, "repair_ocr_numeric_unit", before, value, "low_confidence_numeric_unit_context", 0.88)
    before_merge = value
    value, merged = _merge_visual_lines(value, block.kind)
    if merged:
        _record(document, block, page_num, "merge_visual_lines", before_merge, value, "same_layout_block_without_sentence_boundary", 0.9)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    if block.kind == "text" and _HEADING.match(value) and len(value) <= 160:
        block.kind = "heading"
    elif block.kind == "text" and _LIST.match(value):
        block.kind = "list"
    block.text = value
    return merged, hyphens


def _repeated_edge_text(document: ParsedDocument) -> set[str]:
    page_total = max(len(document.pages), 1)
    counts: Counter[str] = Counter()
    for page in document.pages:
        seen = set()
        for block in page.blocks:
            if block.kind not in {"header", "footer"} or not block.text.strip():
                continue
            normalized = re.sub(r"\d+", "#", re.sub(r"\s+", " ", block.text.strip().lower()))
            seen.add(normalized)
        counts.update(seen)
    threshold = max(2, int(page_total * 0.4 + 0.999))
    return {text for text, count in counts.items() if count >= threshold}


def _recover_sections(document: ParsedDocument) -> list[SectionNode]:
    sections: list[SectionNode] = []
    toc = document.metadata.get("toc") or []
    for index, entry in enumerate(toc):
        if len(entry) >= 3 and str(entry[1]).strip():
            sections.append(SectionNode(
                section_id=f"toc_{index}", title=str(entry[1]).strip(), level=max(1, int(entry[0])),
                start_page=max(1, int(entry[2])), source="toc",
            ))
    if not sections:
        for page in document.pages:
            for block in page.blocks:
                if block.kind == "heading" and block.text:
                    match = re.match(r"^(\d+(?:\.\d+)*)", block.text)
                    level = match.group(1).count(".") + 1 if match else 1
                    sections.append(SectionNode(
                        section_id=hashlib.sha1(f"{page.page_number}:{block.block_id}:{block.text}".encode()).hexdigest()[:16],
                        title=block.text[:300], level=level, start_page=page.page_number,
                        source="layout" if block.spans else "regex",
                    ))
    for index, section in enumerate(sections[:-1]):
        section.end_page = max(section.start_page, sections[index + 1].start_page - 1)
    if sections:
        sections[-1].end_page = document.page_count
    return sections


def _quality_report(document: ParsedDocument, merged: int, hyphens: int, removed: Counter[str], duplicates: int, original_blocks: int) -> DocumentQualityReport:
    classifications = [page.classification for page in document.pages if page.classification]
    confidences = [page.ocr_confidence for page in document.pages if page.ocr_confidence is not None]
    low_pages: list[int] = []
    for page in document.pages:
        valid_ratio = min(1.0, len(re.findall(r"[\w\u4e00-\u9fff]", page.text)) / max(len(page.text.strip()), 1))
        clean_ratio = 1.0 - garbled_ratio(page.text)
        if page.extraction_method in {"ocr", "mixed"}:
            score = 0.62 * float(page.ocr_confidence or 0) + 0.23 * valid_ratio + 0.15 * clean_ratio
        else:
            score = 0.75 * clean_ratio + 0.25 * valid_ratio
        page.quality_score = round(max(0.0, min(score, 1.0)), 4)
        if page.quality_score >= settings.OCR_QUALITY_GOOD_THRESHOLD:
            page.quality_status = "good"
        elif page.quality_score >= settings.OCR_QUALITY_MANUAL_REVIEW_THRESHOLD:
            page.quality_status = "medium"
        else:
            page.quality_status = "manual_review_required"
            low_pages.append(page.page_number)
    page_scores = [page.quality_score or 0 for page in document.pages]
    average = sum(page_scores) / max(len(page_scores), 1)
    overall = "manual_review_required" if low_pages else ("good" if average >= settings.OCR_QUALITY_GOOD_THRESHOLD else "medium")
    warnings = [f"Pages requiring manual review: {low_pages}"] if low_pages else []
    return DocumentQualityReport(
        total_pages=document.page_count,
        embedded_pages=sum(item.page_type == "embedded_text" for item in classifications),
        scanned_pages=sum(item.page_type == "scanned" for item in classifications),
        hybrid_pages=sum(item.page_type == "hybrid" for item in classifications),
        complex_layout_pages=sum(item.page_type == "complex_layout" for item in classifications),
        empty_pages=sum(item.page_type == "empty" for item in classifications),
        average_ocr_confidence=(sum(confidences) / len(confidences) if confidences else None),
        low_quality_pages=low_pages,
        removed_header_count=removed["header"],
        removed_footer_count=removed["footer"],
        removed_watermark_count=removed["watermark"],
        table_count=sum(len(page.tables) for page in document.pages),
        merged_line_count=merged,
        repaired_hyphenation_count=hyphens,
        garbled_character_ratio=sum(garbled_ratio(page.text) for page in document.pages) / max(document.page_count, 1),
        duplicate_block_ratio=duplicates / max(original_blocks, 1),
        overall_quality=overall,  # type: ignore[arg-type]
        warnings=warnings,
    )


def clean_preserving_structure(document: ParsedDocument) -> ParsedDocument:
    document.metadata["raw_blocks"] = [
        {"page_num": page.page_number, "blocks": [asdict(block) for block in page.blocks]}
        for page in document.pages
    ]
    _merge_cross_page_tables(document)
    repeated_edges = _repeated_edge_text(document)
    removed: Counter[str] = Counter()
    merged_total = hyphen_total = duplicate_total = 0
    original_blocks = sum(len(page.blocks) for page in document.pages)
    for page in document.pages:
        seen: set[str] = set()
        cleaned_blocks: list[TextBlock] = []
        for block in page.blocks:
            original = block.text
            normalized_edge = re.sub(r"\d+", "#", re.sub(r"\s+", " ", original.strip().lower()))
            removal_kind = None
            if block.kind in {"header", "footer"} and normalized_edge in repeated_edges:
                removal_kind = block.kind
            elif block.kind == "page_number" or _PAGE_NUMBER.match(original.strip()):
                removal_kind = "page_number"
            elif settings.PDF_WATERMARK_REMOVAL_ENABLED and _WATERMARK.match(original.strip()):
                removal_kind = "watermark"
            if removal_kind and (removal_kind != "header" or settings.PDF_HEADER_FOOTER_REMOVAL_ENABLED):
                removed[removal_kind] += 1
                _record(document, block, page.page_number, f"remove_{removal_kind}", original, "", "repeated_position_or_page_pattern", 0.95)
                continue
            merged, hyphens = _clean_block(document, page.page_number, block)
            merged_total += merged
            hyphen_total += hyphens
            if not block.text and block.kind != "figure":
                continue
            fingerprint = re.sub(r"\W+", "", block.text).lower()
            if fingerprint and fingerprint in seen:
                duplicate_total += 1
                _record(document, block, page.page_number, "remove_duplicate", original, "", "same_page_normalized_hash", 0.98)
                continue
            if fingerprint:
                seen.add(fingerprint)
            cleaned_blocks.append(block)
        for table in page.tables:
            markdown = getattr(table, "markdown", "")
            table_id = getattr(table, "table_id", f"p{page.page_number}_table")
            if markdown:
                cleaned_blocks.append(TextBlock(
                    text=markdown, kind="table", bbox=getattr(table, "bbox", None),
                    order=len(cleaned_blocks), block_id=table_id, extraction_method=getattr(table, "extraction_method", "table"),
                ))
        page.blocks = cleaned_blocks
        page.text = "\n".join(block.text for block in page.blocks if block.text)
    document.sections = _recover_sections(document)
    if settings.DOCUMENT_QUALITY_ASSESSMENT_ENABLED:
        document.quality_report = _quality_report(
            document, merged_total, hyphen_total, removed, duplicate_total, original_blocks
        )
        document.warnings.extend(document.quality_report.warnings)
    else:
        # 清洗、去重、结构恢复照常执行，但不计算质量分数或高/中/低等级。
        document.quality_report = None
        for page in document.pages:
            page.quality_score = None
            page.quality_status = "not_evaluated"
    return document


def _clean(text: str) -> str:
    """Compatibility wrapper used by legacy callers and baseline tests."""
    normalized = normalize_medical_unicode(text)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
