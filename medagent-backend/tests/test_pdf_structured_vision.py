"""Regression coverage for structured tables, visual chunks and vector rebuilds."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fitz

from app.api.v1.documents import rebuild_knowledge_base_vectors
from app.chunking.structural_splitter import StructuralSplitter
from app.parsers.models import ParsedDocument, ParsedPage, TextBlock
from app.parsers.vision_analyzer import PDFVisionAnalyzer


def test_visual_figure_description_is_embedded_as_a_searchable_chunk():
    figure = TextBlock(
        "图表：收缩压变化\n视觉摘要：治疗组较基线下降",
        kind="figure",
        block_id="p1_vision_figure_0",
        extraction_method="pdf-vision-v1",
        metadata={"visual_analysis": True},
    )
    parsed = ParsedDocument(
        "chart.pdf", "pdf", "parser-v4",
        [ParsedPage(1, figure.text, "native", blocks=[figure])],
        metadata={"content_sha256": "chart-hash"},
    )

    chunks = StructuralSplitter(child_tokens=80, parent_tokens=160).split(parsed)

    child = next(chunk for chunk in chunks if chunk.chunk_type == "child")
    assert child.metadata["content_type"] == "figure"
    assert "治疗组" in child.content


def test_vision_result_preserves_table_rows_units_and_footnotes():
    table = PDFVisionAnalyzer._table({
        "title": "血压观察表",
        "headers": ["组别", "收缩压 (mmHg)"],
        "rows": [["治疗组", "120"], ["对照组", "135"]],
        "units": ["mmHg"],
        "footnotes": ["注：均值"],
        "confidence": 0.88,
    }, 3, 0)

    assert table is not None
    assert table.page_start == table.page_end == 3
    assert table.rows[0] == ["治疗组", "120"]
    assert table.units == ["mmHg"]
    assert table.footnotes == ["注：均值"]
    assert "| 治疗组 | 120 |" in table.markdown


def test_complex_chart_detection_uses_vector_drawings():
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=800)
    for offset in range(12):
        page.draw_line((50, 80 + offset * 10), (500, 90 + offset * 10))

    with patch("app.parsers.vision_analyzer.settings.PDF_VISION_MIN_DRAWINGS", 12):
        assert PDFVisionAnalyzer.should_analyze(page, [], "embedded_text")
    pdf.close()


def test_vision_analyzer_reuses_existing_embedding_provider_key():
    with (
        patch("app.parsers.vision_analyzer.settings.PDF_VISION_API_KEY", None),
        patch("app.parsers.vision_analyzer.settings.EMBEDDING_API_KEY", "existing-key"),
        patch("app.parsers.vision_analyzer.settings.LLM_API_KEY", "text-key"),
    ):
        assert PDFVisionAnalyzer._api_key() == "existing-key"


def test_kb_vector_rebuild_force_reparses_and_skips_active_documents():
    ready = SimpleNamespace(
        id=11, kb_id=7, file_path="ready.pdf", file_type="pdf",
        parse_status="success", vector_status="success", error_message=None,
        processing_task_id=None,
    )
    active = SimpleNamespace(
        id=12, kb_id=7, file_path="active.pdf", file_type="pdf",
        parse_status="processing", vector_status="pending", error_message=None,
        processing_task_id="doc-12",
    )
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = [ready, active]
    db = MagicMock()
    db.query.return_value = query
    user = SimpleNamespace(id=3, role="admin", tenant_id=1)

    with (
        patch("app.api.v1.documents.require_kb_write_access"),
        patch("app.api.v1.documents.embedding_service.check_health"),
        patch("app.api.v1.documents.task_manager.get_task", return_value={"status": "started"}),
        patch("app.tasks.document_tasks.enqueue_document", return_value="doc-11-new") as enqueue,
    ):
        result = rebuild_knowledge_base_vectors(7, db, user)

    assert result.scheduled == 1
    assert result.skipped_active == 1
    assert ready.processing_task_id == "doc-11-new"
    enqueue.assert_called_once()
    assert enqueue.call_args.kwargs["force_reparse"] is True
