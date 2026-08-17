"""Optional multimodal analysis for chart-heavy and scanned PDF pages."""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import fitz
import httpx

from app.core.config import settings
from app.parsers.models import ParsedTable, TextBlock


logger = logging.getLogger(__name__)
_JSON_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


@dataclass(slots=True)
class VisionPageResult:
    blocks: list[TextBlock] = field(default_factory=list)
    tables: list[ParsedTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PDFVisionAnalyzer:
    """Turn page pixels into grounded, searchable chart/table descriptions.

    The analyzer is deliberately best-effort. A provider outage or a model that
    does not accept images must never invalidate text/OCR extraction for the PDF.
    """

    version = "pdf-vision-v1"

    @staticmethod
    def _api_key() -> str | None:
        return settings.PDF_VISION_API_KEY or settings.EMBEDDING_API_KEY or settings.LLM_API_KEY

    @staticmethod
    def is_available() -> bool:
        return bool(
            settings.PDF_VISION_ANALYSIS_ENABLED
            and settings.PDF_VISION_MODEL
            and PDFVisionAnalyzer._api_key()
        )

    @staticmethod
    def should_analyze(page: fitz.Page, blocks: list[TextBlock], page_type: str) -> bool:
        page_area = max(float(page.rect.width * page.rect.height), 1.0)
        largest_image_ratio = max(
            (
                ((block.bbox[2] - block.bbox[0]) * (block.bbox[3] - block.bbox[1])) / page_area
                for block in blocks
                if block.kind == "figure" and block.bbox
            ),
            default=0.0,
        )
        text = "\n".join(block.text for block in blocks if block.text)
        has_chart_caption = bool(re.search(
            r"(?:^|\n)\s*(?:图|图表|figure|fig\.?|chart)\s*[A-Za-z0-9一二三四五六七八九十.-]*",
            text,
            re.IGNORECASE,
        ))
        try:
            drawing_count = len(page.get_drawings())
        except Exception:
            drawing_count = 0
        return bool(
            page_type in {"scanned", "complex_layout"}
            or largest_image_ratio >= settings.PDF_VISION_MIN_IMAGE_COVERAGE
            or drawing_count >= settings.PDF_VISION_MIN_DRAWINGS
            or has_chart_caption
        )

    @staticmethod
    def _render_data_url(page: fitz.Page) -> str:
        dpi = min(max(int(settings.PDF_VISION_DPI), 96), 240)
        scale = dpi / 72.0
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    @staticmethod
    def _content_text(message_content: Any) -> str:
        if isinstance(message_content, str):
            return message_content
        if isinstance(message_content, list):
            return "\n".join(
                str(item.get("text", ""))
                for item in message_content
                if isinstance(item, dict)
            )
        return str(message_content or "")

    @staticmethod
    def _load_json(raw: str) -> dict[str, Any]:
        cleaned = _JSON_FENCE.sub("", raw.strip()).strip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise ValueError("vision model did not return JSON")
            value = json.loads(cleaned[start:end + 1])
        if not isinstance(value, dict):
            raise ValueError("vision model returned a non-object payload")
        return value

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @classmethod
    def _figure_block(cls, item: dict[str, Any], page_number: int, index: int) -> TextBlock | None:
        summary = str(item.get("summary") or "").strip()
        if not summary:
            return None
        title = str(item.get("title") or f"第 {page_number} 页图表 {index + 1}").strip()
        figure_type = str(item.get("figure_type") or "complex_chart").strip()
        axes = cls._string_list(item.get("axes"))
        legends = cls._string_list(item.get("legends"))
        trends = cls._string_list(item.get("trends"))
        findings = cls._string_list(item.get("numeric_findings"))
        cautions = cls._string_list(item.get("cautions"))
        lines = [f"图表：{title}", f"类型：{figure_type}", f"视觉摘要：{summary}"]
        for label, values in (
            ("坐标轴", axes), ("图例", legends), ("趋势", trends),
            ("数值发现", findings), ("解读限制", cautions),
        ):
            if values:
                lines.append(f"{label}：" + "；".join(values))
        confidence = float(item.get("confidence") or 0.0)
        return TextBlock(
            text="\n".join(lines),
            kind="figure",
            confidence=max(0.0, min(confidence, 1.0)),
            block_id=f"p{page_number}_vision_figure_{index}",
            extraction_method=cls.version,
            metadata={
                "visual_analysis": True,
                "figure_type": figure_type,
                "title": title,
                "axes": axes,
                "legends": legends,
                "trends": trends,
                "numeric_findings": findings,
                "cautions": cautions,
                "model": settings.PDF_VISION_MODEL,
            },
        )

    @classmethod
    def _table(cls, item: dict[str, Any], page_number: int, index: int) -> ParsedTable | None:
        headers = cls._string_list(item.get("headers"))
        raw_rows = item.get("rows")
        if not headers or not isinstance(raw_rows, list):
            return None
        width = len(headers)
        rows: list[list[str]] = []
        for raw_row in raw_rows:
            if not isinstance(raw_row, list):
                continue
            row = [str(cell or "").strip() for cell in raw_row[:width]]
            rows.append(row + [""] * (width - len(row)))
        if not rows:
            return None
        escaped_headers = [cell.replace("|", "\\|") for cell in headers]
        markdown = [
            "| " + " | ".join(escaped_headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        markdown.extend(
            "| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |"
            for row in rows
        )
        confidence = float(item.get("confidence") or 0.0)
        return ParsedTable(
            table_id=f"p{page_number}_vision_table_{index}",
            title=str(item.get("title") or "").strip() or None,
            page_start=page_number,
            page_end=page_number,
            section_path=[],
            headers=headers,
            rows=rows,
            units=cls._string_list(item.get("units")),
            footnotes=cls._string_list(item.get("footnotes")),
            markdown="\n".join(markdown),
            extraction_method=cls.version,
            confidence=max(0.0, min(confidence, 1.0)),
        )

    def analyze_page(self, page: fitz.Page, page_number: int) -> VisionPageResult:
        if not self.is_available():
            return VisionPageResult()
        endpoint = settings.PDF_VISION_API_BASE.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        prompt = (
            "分析这张医学 PDF 页面。只报告图中明确可见的信息，禁止补造数据、单位、趋势或临床结论。"
            "抽取所有复杂图表的标题、类型、坐标轴、图例、趋势、明确标注的关键数值和解读限制；"
            "同时把图片或扫描页中的表格按原始行列抽取，缺失单元格使用空字符串，不合并或推断单元格。"
            "返回严格 JSON 对象："
            '{"figures":[{"title":"","figure_type":"","summary":"","axes":[],"legends":[],"trends":[],"numeric_findings":[],"cautions":[],"confidence":0.0}],'
            '"tables":[{"title":"","headers":[],"rows":[[]],"units":[],"footnotes":[],"confidence":0.0}]}。'
            "没有图表或表格时对应数组返回空数组。"
        )
        payload = {
            "model": settings.PDF_VISION_MODEL,
            "temperature": 0,
            "max_tokens": int(settings.PDF_VISION_MAX_OUTPUT_TOKENS),
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": self._render_data_url(page), "detail": "high",
                    }},
                ],
            }],
        }
        try:
            with httpx.Client(timeout=float(settings.PDF_VISION_TIMEOUT_SECONDS)) as client:
                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {self._api_key()}"},
                    json=payload,
                )
                response.raise_for_status()
            body = response.json()
            raw = self._content_text(body["choices"][0]["message"]["content"])
            parsed = self._load_json(raw)
            blocks = [
                block for index, item in enumerate(parsed.get("figures") or [])
                if isinstance(item, dict)
                for block in [self._figure_block(item, page_number, index)]
                if block is not None
            ]
            tables = [
                table for index, item in enumerate(parsed.get("tables") or [])
                if isinstance(item, dict)
                for table in [self._table(item, page_number, index)]
                if table is not None
            ]
            return VisionPageResult(blocks=blocks, tables=tables)
        except Exception as exc:
            logger.warning("PDF vision analysis skipped for page %s: %s", page_number, exc)
            return VisionPageResult(warnings=[f"第 {page_number} 页视觉分析失败，已保留文本/OCR结果：{exc}"])


pdf_vision_analyzer = PDFVisionAnalyzer()
