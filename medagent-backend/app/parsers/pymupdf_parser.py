"""Coordinate-aware PyMuPDF parser with classified page-level OCR."""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median

import fitz

from app.core.config import settings
from app.parsers.base import ParseProgress
from app.parsers.easyocr_parser import EasyOCRParser
from app.parsers.models import OCRSpan, ParsedDocument, ParsedPage, ParsedTable, TextBlock, TextSpan
from app.parsers.page_classifier import classify_page
from app.parsers.vision_analyzer import pdf_vision_analyzer


class PyMuPDFParser:
    version = "pymupdf-layout-v4-structured-vision"

    def __init__(self, ocr_parser: EasyOCRParser | None = None) -> None:
        self.ocr_parser = ocr_parser or EasyOCRParser()

    @staticmethod
    def _block_kind(text: str, spans: list[TextSpan], median_size: float, bbox, page: fitz.Page) -> str:
        stripped = text.strip()
        y0, y1 = bbox[1], bbox[3]
        height = float(page.rect.height)
        if re.fullmatch(r"(?:-\s*)?\d+(?:\s*-)?|第\s*\d+\s*页|Page\s+\d+(?:\s+of\s+\d+)?", stripped, re.I):
            return "page_number"
        if y0 <= height * 0.08:
            return "header"
        if y1 >= height * 0.92:
            return "footer"
        if re.match(r"^(?:[-•●▪◦]|\d+[.)]|[一二三四五六七八九十]+[、.]|\([一二三四五六七八九十\d]+\))\s*", stripped):
            return "list"
        if re.match(r"^(?:参考文献|References)\s*$", stripped, re.I):
            return "heading"
        max_size = max((span.font_size or 0 for span in spans), default=0)
        bold = any(span.is_bold for span in spans)
        if stripped and (max_size >= median_size * 1.32 or (bold and max_size >= median_size * 1.1)):
            return "heading"
        if max_size and max_size <= median_size * 0.78 and y0 >= height * 0.7:
            return "footnote"
        return "text"

    @classmethod
    def _native_blocks(cls, page: fitz.Page) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        raw = page.get_text("dict", sort=False)
        font_sizes: list[float] = []
        prepared: list[tuple[dict, list[TextSpan], str]] = []
        for item in raw.get("blocks", []):
            if item.get("type") == 1:
                bbox = tuple(float(value) for value in item.get("bbox", (0, 0, 0, 0)))
                blocks.append(TextBlock("", kind="figure", bbox=bbox, metadata={"image": True}))
                continue
            spans: list[TextSpan] = []
            lines: list[str] = []
            for line in item.get("lines", []):
                line_text: list[str] = []
                for raw_span in line.get("spans", []):
                    text = str(raw_span.get("text", ""))
                    if not text:
                        continue
                    size = float(raw_span.get("size") or 0)
                    font_sizes.append(size)
                    font = str(raw_span.get("font") or "") or None
                    flags = int(raw_span.get("flags") or 0)
                    spans.append(TextSpan(
                        text=text,
                        bbox=tuple(float(value) for value in raw_span.get("bbox", (0, 0, 0, 0))),
                        font=font,
                        font_size=size or None,
                        is_bold=bool(flags & 16) or bool(font and "bold" in font.lower()),
                        is_italic=bool(flags & 2) or bool(font and "italic" in font.lower()),
                        color=raw_span.get("color"),
                    ))
                    line_text.append(text)
                if line_text:
                    lines.append("".join(line_text).strip())
            text = "\n".join(value for value in lines if value).strip()
            if text:
                prepared.append((item, spans, text))

        median_size = median([value for value in font_sizes if value > 0]) if font_sizes else 10.0
        for item, spans, text in prepared:
            bbox = tuple(float(value) for value in item.get("bbox", (0, 0, 0, 0)))
            blocks.append(TextBlock(
                text=text,
                kind=cls._block_kind(text, spans, median_size, bbox, page),  # type: ignore[arg-type]
                bbox=bbox,
                spans=spans,
                extraction_method="native",
            ))
        return cls._reading_order(blocks, float(page.rect.width), page.number + 1)

    @staticmethod
    def _reading_order(blocks: list[TextBlock], page_width: float, page_number: int) -> list[TextBlock]:
        text_blocks = [block for block in blocks if block.bbox and block.kind != "figure"]
        narrow = [block for block in text_blocks if (block.bbox[2] - block.bbox[0]) < page_width * 0.72]
        left = [block for block in narrow if (block.bbox[0] + block.bbox[2]) / 2 < page_width / 2]
        right = [block for block in narrow if (block.bbox[0] + block.bbox[2]) / 2 >= page_width / 2]
        if len(left) >= 2 and len(right) >= 2:
            wide = [block for block in blocks if block not in narrow]
            ordered = sorted(wide, key=lambda block: ((block.bbox or (0, 0, 0, 0))[1], (block.bbox or (0, 0, 0, 0))[0]))
            ordered += sorted(left, key=lambda block: (block.bbox[1], block.bbox[0]))
            ordered += sorted(right, key=lambda block: (block.bbox[1], block.bbox[0]))
        else:
            ordered = sorted(blocks, key=lambda block: ((block.bbox or (0, 0, 0, 0))[1], (block.bbox or (0, 0, 0, 0))[0]))
        for order, block in enumerate(ordered):
            block.order = order
            block.block_id = f"p{page_number}_b{order}"
        return ordered

    @staticmethod
    def _extract_tables(page: fitz.Page) -> list[ParsedTable]:
        if not settings.PDF_TABLE_EXTRACTION_ENABLED or not hasattr(page, "find_tables"):
            return []
        try:
            finder = page.find_tables()
        except Exception:
            return []
        result: list[ParsedTable] = []
        page_blocks = page.get_text("blocks", sort=True)
        for index, table in enumerate(getattr(finder, "tables", []) or []):
            rows = [[str(cell or "").strip() for cell in row] for row in (table.extract() or [])]
            if not rows:
                continue
            bbox = tuple(float(value) for value in getattr(table, "bbox", (0, 0, 0, 0)))
            width = max(len(row) for row in rows)
            normalized = [row[:width] + [""] * (width - len(row)) for row in rows]
            headers, body = normalized[0], normalized[1:]
            escaped_headers = [cell.replace("|", "\\|") for cell in headers]
            markdown = [
                "| " + " | ".join(escaped_headers) + " |",
                "| " + " | ".join("---" for _ in headers) + " |",
            ]
            markdown.extend(
                "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
                for row in body
            )
            above = [
                (float(item[3]), str(item[4]).strip())
                for item in page_blocks
                if str(item[4]).strip() and float(item[3]) <= bbox[1] + 2
                and bbox[1] - float(item[3]) <= 90
            ]
            title = max(above, default=(0.0, ""), key=lambda item: item[0])[1] or None
            below = [
                str(item[4]).strip()
                for item in page_blocks
                if str(item[4]).strip() and float(item[1]) >= bbox[3] - 2
                and float(item[1]) - bbox[3] <= 80
            ]
            footnotes = [
                value for value in below
                if re.match(r"^(?:注|备注|说明|Note|\*|†)", value, re.IGNORECASE)
            ]
            unit_pattern = re.compile(
                r"(?:mg(?:/mL|/dL)?|μg|ug|mmHg|mmol/L|mol/L|g/L|IU/L|U/L|%|cm|mm|kg|mL|L|次/日)",
                re.IGNORECASE,
            )
            units = list(dict.fromkeys(
                match.group(0)
                for row in normalized for cell in row for match in unit_pattern.finditer(cell)
            ))
            result.append(ParsedTable(
                table_id=f"p{page.number + 1}_t{index}", title=title,
                page_start=page.number + 1, page_end=page.number + 1, section_path=[],
                headers=headers, rows=body, units=units, footnotes=footnotes, markdown="\n".join(markdown),
                extraction_method="pymupdf", confidence=0.9, bbox=bbox,
            ))
        return result

    @staticmethod
    def _merge_vision_tables(native: list[ParsedTable], visual: list[ParsedTable]) -> list[ParsedTable]:
        result = list(native)
        fingerprints = {
            re.sub(r"\W+", "", "|".join(table.headers + [cell for row in table.rows[:2] for cell in row])).lower()
            for table in native
        }
        for table in visual:
            fingerprint = re.sub(
                r"\W+", "", "|".join(table.headers + [cell for row in table.rows[:2] for cell in row])
            ).lower()
            if fingerprint and fingerprint in fingerprints:
                continue
            result.append(table)
            if fingerprint:
                fingerprints.add(fingerprint)
        return result

    @staticmethod
    def _merge_hybrid(native: list[TextBlock], ocr: list[TextBlock], page_number: int) -> list[TextBlock]:
        merged = list(native)
        normalized_native = [re.sub(r"\W+", "", item.text).lower() for item in native]
        for block in ocr:
            normalized = re.sub(r"\W+", "", block.text).lower()
            duplicate = any(
                normalized and existing and SequenceMatcher(None, normalized, existing).ratio() >= 0.88
                for existing in normalized_native
            )
            if not duplicate:
                block.extraction_method = "ocr"
                block.block_id = f"p{page_number}_ocr{len(merged)}"
                merged.append(block)
        return sorted(merged, key=lambda block: ((block.bbox or (0, 0, 0, 0))[1], (block.bbox or (0, 0, 0, 0))[0]))

    def parse(self, file_path: str, progress_callback: ParseProgress | None = None) -> ParsedDocument:
        pages: list[ParsedPage] = []
        warnings: list[str] = []
        ocr_count = 0
        vision_count = 0
        pdf_metadata: dict = {}
        toc: list = []

        try:
            with fitz.open(file_path) as pdf:
                if pdf.needs_pass:
                    raise ValueError("PDF is encrypted and requires a password")
                if pdf.page_count == 0:
                    raise ValueError("PDF has no pages")
                pdf_metadata = dict(pdf.metadata or {})
                toc = pdf.get_toc(simple=True)
                for page_number, page in enumerate(pdf, start=1):
                    native_blocks = self._native_blocks(page)
                    native_text = "\n".join(block.text for block in native_blocks if block.text).strip()
                    tables = self._extract_tables(page)
                    classification = classify_page(page, native_blocks, len(tables))
                    use_ocr = bool(settings.OCR_ENABLED and classification.requires_ocr)
                    page_warnings: list[str] = []
                    blocks = native_blocks
                    text = native_text
                    confidence = None
                    method = "native"

                    if use_ocr:
                        ocr_count += 1
                        if ocr_count > max(settings.OCR_MAX_PAGES, 1):
                            raise ValueError(f"OCR page count exceeds OCR_MAX_PAGES={settings.OCR_MAX_PAGES}")
                        try:
                            dpi = min(max(settings.OCR_DPI_DEFAULT, settings.OCR_DPI, 72), settings.OCR_DPI_MAX)
                            ocr_text, ocr_blocks, confidence = self.ocr_parser.parse_page(page, dpi)
                            for block in ocr_blocks:
                                block.extraction_method = "ocr"
                        except Exception as exc:
                            raise RuntimeError(f"OCR failed on PDF page {page_number}/{pdf.page_count}: {exc}") from exc
                        if ocr_text.strip():
                            if classification.extraction_mode == "hybrid" and native_text:
                                blocks = self._merge_hybrid(native_blocks, ocr_blocks, page_number)
                                text = "\n".join(block.text for block in blocks if block.text).strip()
                                method = "mixed"
                            else:
                                text, blocks, method = ocr_text.strip(), ocr_blocks, "ocr"
                        elif native_text:
                            page_warnings.append("OCR returned no text; retained sparse native text")
                        else:
                            method = "ocr"
                            page_warnings.append("OCR returned no text")

                    vision_limit = int(settings.PDF_VISION_MAX_PAGES)
                    if (
                        pdf_vision_analyzer.is_available()
                        and (vision_limit <= 0 or vision_count < vision_limit)
                        and pdf_vision_analyzer.should_analyze(
                            page, blocks, classification.page_type,
                        )
                    ):
                        vision_count += 1
                        visual = pdf_vision_analyzer.analyze_page(page, page_number)
                        if visual.blocks:
                            blocks = self._reading_order(
                                blocks + visual.blocks,
                                float(page.rect.width),
                                page_number,
                            )
                            text = "\n".join(block.text for block in blocks if block.text).strip()
                        tables = self._merge_vision_tables(tables, visual.tables)
                        page_warnings.extend(visual.warnings)

                    pages.append(ParsedPage(
                        page_number=page_number,
                        text=text,
                        extraction_method=method,  # type: ignore[arg-type]
                        blocks=blocks,
                        tables=tables,
                        ocr_confidence=confidence,
                        width=float(page.rect.width),
                        height=float(page.rect.height),
                        warnings=page_warnings,
                        raw_text=native_text,
                        classification=classification,
                        ocr_spans=[OCRSpan(
                            text=block.text,
                            bbox=[[block.bbox[0], block.bbox[1]], [block.bbox[2], block.bbox[1]], [block.bbox[2], block.bbox[3]], [block.bbox[0], block.bbox[3]]],
                            confidence=float(block.confidence or 0),
                            language=None,
                            page_num=page_number,
                        ) for block in blocks if block.extraction_method == "ocr" and block.bbox],
                    ))
                    if progress_callback:
                        progress_callback(page_number, pdf.page_count, use_ocr)
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise ValueError(f"PDF parse error: {exc}") from exc

        if not any(page.text.strip() for page in pages):
            raise ValueError("PDF parsing and OCR produced no text")
        path = Path(file_path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        return ParsedDocument(
            source_path=str(path),
            file_type="pdf",
            parser_version=settings.PDF_PARSER_VERSION or self.version,
            cleaning_version=settings.PDF_CLEANING_VERSION,
            pages=pages,
            warnings=warnings,
            metadata={
                "content_sha256": digest,
                "file_size": path.stat().st_size,
                "mime_type": "application/pdf",
                "pdf_metadata": pdf_metadata,
                "toc": toc,
                "vision_analyzed_pages": vision_count,
                "vision_version": pdf_vision_analyzer.version,
            },
        )
