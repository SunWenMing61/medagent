"""Persistence and review operations for Raw/Clean PDF processing layers."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_processing import (
    DocumentCleanBlock, DocumentCleaningActionRecord, DocumentPage,
    DocumentQualityReportRecord, DocumentRawBlock, DocumentTable,
)
from app.parsers.models import ParsedDocument, ParsedPage, TextBlock


logger = logging.getLogger(__name__)


class DocumentProcessingService:
    @staticmethod
    def _section_path(parsed: ParsedDocument, page_num: int) -> list[str]:
        active = [section for section in parsed.sections if section.start_page <= page_num <= (section.end_page or page_num)]
        if not active:
            return []
        target = active[-1]
        return [item.title for item in parsed.sections if item.start_page <= target.start_page and item.level <= target.level][-target.level:]

    def replace_layers(self, db: Session, document: Document, parsed: ParsedDocument) -> None:
        document_id = int(document.id)
        quality_was_approved = document.quality_status == "approved"
        for model in (
            DocumentCleaningActionRecord, DocumentTable, DocumentCleanBlock,
            DocumentRawBlock, DocumentPage, DocumentQualityReportRecord,
        ):
            db.query(model).filter(model.document_id == document_id).delete(synchronize_session=False)

        raw_map: dict[str, int] = {}
        raw_pages = {item["page_num"]: item["blocks"] for item in parsed.metadata.get("raw_blocks", [])}
        for page in parsed.pages:
            classification = asdict(page.classification) if page.classification else {
                "page_num": page.page_number, "page_type": "embedded_text",
            }
            db.add(DocumentPage(
                document_id=document_id,
                page_num=page.page_number,
                page_type=classification.get("page_type", "embedded_text"),
                extraction_method=page.extraction_method,
                raw_text=page.raw_text,
                cleaned_text=page.text,
                width=page.width,
                height=page.height,
                classification_json=classification,
                ocr_spans_json=[asdict(item) for item in page.ocr_spans] or None,
                ocr_confidence=page.ocr_confidence,
                quality_score=page.quality_score,
                quality_status=page.quality_status,
                warnings_json=page.warnings or None,
                metadata_json=page.metadata or None,
            ))
            for raw in raw_pages.get(page.page_number, []):
                block_id = raw.get("block_id") or f"p{page.page_number}_b{raw.get('order', 0)}"
                row = DocumentRawBlock(
                    document_id=document_id,
                    page_num=page.page_number,
                    block_id=block_id,
                    block_type=raw.get("kind", "unknown"),
                    text=raw.get("text", ""),
                    bbox_json=raw.get("bbox"),
                    spans_json=raw.get("spans") or None,
                    reading_order=int(raw.get("order") or 0),
                    extraction_method=raw.get("extraction_method") or page.extraction_method,
                    confidence=raw.get("confidence"),
                    metadata_json=raw.get("metadata") or None,
                )
                db.add(row)
                db.flush()
                raw_map[block_id] = int(row.id)
            section_path = self._section_path(parsed, page.page_number)
            for block in page.blocks:
                db.add(DocumentCleanBlock(
                    document_id=document_id,
                    raw_block_id=raw_map.get(block.block_id),
                    page_num=page.page_number,
                    block_id=block.block_id or f"p{page.page_number}_b{block.order}",
                    block_type=block.kind,
                    text=block.text,
                    bbox_json=block.bbox,
                    section_path_json=section_path or None,
                    reading_order=block.order,
                    extraction_method=block.extraction_method,
                    metadata_json=block.metadata or None,
                ))
            for table in page.tables:
                if not hasattr(table, "table_id"):
                    continue
                db.add(DocumentTable(
                    document_id=document_id,
                    table_id=table.table_id,
                    title=table.title,
                    page_start=table.page_start,
                    page_end=table.page_end,
                    section_path_json=table.section_path or section_path or None,
                    headers_json=table.headers,
                    rows_json=table.rows,
                    units_json=table.units or None,
                    footnotes_json=table.footnotes or None,
                    markdown=table.markdown,
                    bbox_json=table.bbox,
                    extraction_method=table.extraction_method,
                    confidence=table.confidence,
                ))
        for action in parsed.cleaning_actions:
            db.add(DocumentCleaningActionRecord(document_id=document_id, **asdict(action)))
        if parsed.quality_report:
            report = asdict(parsed.quality_report)
            needs_review = parsed.quality_report.overall_quality == "manual_review_required"
            db.add(DocumentQualityReportRecord(
                document_id=document_id,
                report_json=report,
                overall_quality=parsed.quality_report.overall_quality,
                average_ocr_confidence=parsed.quality_report.average_ocr_confidence,
                low_quality_pages_json=parsed.quality_report.low_quality_pages or None,
                warnings_json=parsed.quality_report.warnings or None,
                review_status="approved" if needs_review and quality_was_approved else ("pending" if needs_review else "not_required"),
            ))
            document.quality_status = "approved" if needs_review and quality_was_approved else parsed.quality_report.overall_quality
        else:
            document.quality_status = "not_evaluated"
        document.cleaning_version = parsed.cleaning_version
        document.normalized_text_sha256 = hashlib.sha256(parsed.text.encode("utf-8")).hexdigest()

    def load_parsed_checkpoint(
        self,
        db: Session,
        document: Document,
    ) -> ParsedDocument | None:
        """Restore the persisted clean-text layer without opening the source PDF again.

        Parsing/OCR is the expensive, deterministic first stage of ingestion.  A
        later embedding or pgvector failure must not send a large scanned PDF back
        through OCR.  The normalized text hash makes this checkpoint safe: if the
        stored pages are incomplete or were changed, the hash check fails and the
        caller performs a fresh parse.
        """
        if not document.normalized_text_sha256 or not document.parser_version:
            return None

        page_rows = db.query(DocumentPage).filter(
            DocumentPage.document_id == int(document.id)
        ).order_by(DocumentPage.page_num.asc()).all()
        if not page_rows:
            return None

        block_rows = db.query(DocumentCleanBlock).filter(
            DocumentCleanBlock.document_id == int(document.id)
        ).order_by(
            DocumentCleanBlock.page_num.asc(),
            DocumentCleanBlock.reading_order.asc(),
            DocumentCleanBlock.id.asc(),
        ).all()
        blocks_by_page: dict[int, list[TextBlock]] = {}
        for row in block_rows:
            blocks_by_page.setdefault(int(row.page_num), []).append(TextBlock(
                text=row.text,
                kind=row.block_type,
                bbox=tuple(row.bbox_json) if row.bbox_json else None,
                order=int(row.reading_order or 0),
                metadata=row.metadata_json or {},
                block_id=row.block_id,
                extraction_method=row.extraction_method or "native",
            ))

        pages = [ParsedPage(
            page_number=int(row.page_num),
            text=row.cleaned_text or "",
            raw_text=row.raw_text or "",
            extraction_method=row.extraction_method or "native",
            blocks=blocks_by_page.get(int(row.page_num), []),
            ocr_confidence=row.ocr_confidence,
            width=row.width,
            height=row.height,
            warnings=row.warnings_json or [],
            quality_score=row.quality_score,
            quality_status=row.quality_status or "not_evaluated",
            metadata=row.metadata_json or {},
        ) for row in page_rows]

        checkpoint = ParsedDocument(
            source_path=document.file_path or "",
            file_type=document.file_type,
            parser_version=document.parser_version,
            pages=pages,
            warnings=document.processing_warnings or [],
            metadata={
                "content_sha256": document.content_sha256,
                "checkpoint": True,
            },
            cleaning_version=document.cleaning_version or "cleaning-v1",
        )
        actual_hash = hashlib.sha256(checkpoint.text.encode("utf-8")).hexdigest()
        if actual_hash != document.normalized_text_sha256:
            logger.warning(
                "Ignoring incomplete parsed checkpoint for document_id=%s: expected=%s actual=%s",
                document.id,
                document.normalized_text_sha256,
                actual_hash,
            )
            return None
        return checkpoint


document_processing_service = DocumentProcessingService()
