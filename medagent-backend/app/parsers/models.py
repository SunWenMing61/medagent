"""Lossless, serializable parser result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional


ExtractionMethod = Literal["native", "ocr", "mixed", "docx", "text"]
BlockKind = Literal[
    "text", "title", "heading", "list", "table", "figure", "caption",
    "header", "footer", "page_number", "watermark", "footnote", "reference", "unknown",
]
PageType = Literal[
    "embedded_text", "scanned", "hybrid", "table_heavy", "complex_layout", "empty", "garbled",
]


@dataclass(slots=True)
class TextSpan:
    text: str
    bbox: tuple[float, float, float, float]
    font: str | None = None
    font_size: float | None = None
    is_bold: bool = False
    is_italic: bool = False
    confidence: float | None = None
    color: int | None = None


@dataclass(slots=True)
class OCRSpan:
    text: str
    bbox: list[list[float]]
    confidence: float
    language: str | None
    page_num: int


@dataclass(slots=True)
class PageClassification:
    page_num: int
    page_type: PageType
    embedded_char_count: int
    image_count: int
    image_coverage_ratio: float
    text_block_count: int
    table_count: int
    garbled_ratio: float
    requires_ocr: bool
    extraction_mode: Literal["embedded_only", "ocr_only", "hybrid"]
    reason: str


@dataclass(slots=True)
class CleaningAction:
    action_type: str
    original_text: str
    cleaned_text: str
    rule: str
    confidence: float
    page_num: int
    block_id: str


@dataclass(slots=True)
class ParsedTable:
    table_id: str
    title: str | None
    page_start: int
    page_end: int
    section_path: list[str]
    headers: list[str]
    rows: list[list[str]]
    units: list[str]
    footnotes: list[str]
    markdown: str
    extraction_method: str
    confidence: float
    bbox: tuple[float, float, float, float] | None = None


@dataclass(slots=True)
class SectionNode:
    section_id: str
    title: str
    level: int
    start_page: int
    end_page: int | None = None
    parent_section_id: str | None = None
    source: Literal["toc", "layout", "regex", "manual"] = "layout"


@dataclass(slots=True)
class DocumentQualityReport:
    total_pages: int
    embedded_pages: int = 0
    scanned_pages: int = 0
    hybrid_pages: int = 0
    complex_layout_pages: int = 0
    empty_pages: int = 0
    average_ocr_confidence: float | None = None
    low_quality_pages: list[int] = field(default_factory=list)
    removed_header_count: int = 0
    removed_footer_count: int = 0
    removed_watermark_count: int = 0
    table_count: int = 0
    merged_line_count: int = 0
    repaired_hyphenation_count: int = 0
    garbled_character_ratio: float = 0.0
    duplicate_block_ratio: float = 0.0
    overall_quality: Literal["good", "medium", "low", "manual_review_required"] = "good"
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TextBlock:
    text: str
    kind: BlockKind = "text"
    bbox: Optional[tuple[float, float, float, float]] = None
    confidence: Optional[float] = None
    order: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    block_id: str = ""
    spans: list[TextSpan] = field(default_factory=list)
    extraction_method: str = "native"


@dataclass(slots=True)
class ParsedPage:
    page_number: int
    text: str
    extraction_method: ExtractionMethod
    blocks: list[TextBlock] = field(default_factory=list)
    tables: list[ParsedTable | list[list[str]]] = field(default_factory=list)
    ocr_confidence: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""
    classification: PageClassification | None = None
    ocr_spans: list[OCRSpan] = field(default_factory=list)
    quality_score: float | None = None
    quality_status: str = "not_evaluated"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ParsedDocument:
    source_path: str
    file_type: str
    parser_version: str
    pages: list[ParsedPage]
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    cleaning_version: str = "cleaning-v1"
    cleaning_actions: list[CleaningAction] = field(default_factory=list)
    sections: list[SectionNode] = field(default_factory=list)
    quality_report: DocumentQualityReport | None = None

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def ocr_page_count(self) -> int:
        return sum(page.extraction_method in {"ocr", "mixed"} for page in self.pages)

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def legacy_pages(self) -> list[tuple[int, str]]:
        return [(page.page_number, page.text) for page in self.pages if page.text]

    @classmethod
    def empty(cls, source_path: str, file_type: str, parser_version: str) -> "ParsedDocument":
        return cls(str(Path(source_path)), file_type, parser_version, [])
