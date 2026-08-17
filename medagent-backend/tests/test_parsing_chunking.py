"""Regression coverage for typed parsing and structural chunking."""

import fitz

from app.chunking.structural_splitter import StructuralSplitter
from app.models.document_chunk import DocumentChunk
from app.parsers.models import ParsedDocument, ParsedPage, TextBlock
from app.parsers.pymupdf_parser import PyMuPDFParser


class _FakeOCR:
    def parse_page(self, page, dpi):
        del page, dpi
        block = TextBlock("OCR 医疗文本", bbox=(1.0, 2.0, 30.0, 12.0), confidence=0.91)
        return block.text, [block], 0.91


def test_typed_mixed_pdf_preserves_ocr_provenance(tmp_path):
    path = tmp_path / "mixed.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "native medical text " * 10)
    pdf.new_page()
    pdf.save(path)
    pdf.close()

    progress = []
    parsed = PyMuPDFParser(_FakeOCR()).parse(
        str(path), lambda done, total, ocr: progress.append((done, total, ocr))
    )

    assert parsed.page_count == 2
    assert parsed.ocr_page_count == 1
    assert parsed.pages[0].extraction_method == "native"
    assert parsed.pages[1].extraction_method == "ocr"
    assert parsed.pages[1].ocr_confidence == 0.91
    assert parsed.pages[1].blocks[0].bbox == (1.0, 2.0, 30.0, 12.0)
    assert progress == [(1, 2, False), (2, 2, True)]


def test_structural_chunks_are_deterministic_and_page_scoped():
    document = ParsedDocument(
        source_path="sample.md",
        file_type="md",
        parser_version="test-parser-v1",
        metadata={"content_sha256": "abc"},
        pages=[
            ParsedPage(
                1,
                "# 诊断\n第一段医学内容。第二段医学内容。",
                "text",
                blocks=[
                    TextBlock("诊断", kind="heading"),
                    TextBlock("第一段医学内容。第二段医学内容。"),
                ],
            ),
            ParsedPage(2, "治疗方案与随访建议。", "text", blocks=[TextBlock("治疗方案与随访建议。")]),
        ],
    )
    splitter = StructuralSplitter(child_tokens=8, parent_tokens=20, overlap_tokens=2)

    first = splitter.split(document)
    second = splitter.split(document)

    assert [item.logical_id for item in first] == [item.logical_id for item in second]
    assert {item.page_start for item in first} == {1, 2}
    parent_ids = {item.logical_id for item in first if item.chunk_type == "parent"}
    children = [item for item in first if item.chunk_type == "child"]
    assert children
    assert all(item.parent_logical_id in parent_ids for item in children)
    assert all(item.token_count <= 8 for item in children)


def test_duplicate_sections_receive_distinct_logical_ids():
    page = ParsedPage(
        1, "重复。\n重复。", "text",
        blocks=[TextBlock("A", kind="heading"), TextBlock("重复。"), TextBlock("A", kind="heading"), TextBlock("重复。")],
    )
    chunks = StructuralSplitter(child_tokens=20, parent_tokens=30).split(
        ParsedDocument("x", "txt", "v1", [page], metadata={"content_sha256": "same"})
    )
    ids = [chunk.logical_id for chunk in chunks]
    assert len(ids) == len(set(ids))


def test_logical_chunk_id_is_unique_only_within_a_document():
    constraint = next(
        item
        for item in DocumentChunk.__table__.constraints
        if item.name == "uq_document_chunk_document_logical"
    )
    assert [column.name for column in constraint.columns] == ["document_id", "logical_id"]
    assert not DocumentChunk.__table__.c.logical_id.unique


def test_hybrid_chunker_prefers_low_cohesion_topic_boundary():
    text = (
        "Hypertension management includes blood pressure monitoring. "
        "Blood pressure targets depend on cardiovascular risk. "
        "Antihypertensive therapy requires follow-up.\n\n"
        "Dermatology care includes sunscreen and skin examination. "
        "Skin lesions should be assessed for changes. "
        "Dermatology follow-up depends on pathology."
    )
    chunks = StructuralSplitter._pack(text, limit=24, overlap=0)
    assert len(chunks) >= 2
    assert "Antihypertensive therapy" in chunks[0]
    assert "Dermatology care" not in chunks[0]
    assert chunks[1].startswith("Dermatology care")


def test_hybrid_chunker_preserves_table_header_and_marks_strategy():
    page = ParsedPage(
        1, "指标 | 数值\n--- | ---\n血压 | 120\n血糖 | 5.6\n心率 | 70", "text",
        blocks=[TextBlock("指标 | 数值\n--- | ---\n血压 | 120\n血糖 | 5.6\n心率 | 70", kind="table")],
    )
    chunks = StructuralSplitter(child_tokens=8, parent_tokens=20, overlap_tokens=1).split(
        ParsedDocument("table.md", "md", "v1", [page], metadata={"content_sha256": "table"})
    )
    children = [item for item in chunks if item.chunk_type == "child"]
    assert children
    assert all(item.content.startswith("指标 | 数值\n--- | ---") for item in children)
    assert all(item.metadata["chunking_strategy"] == "structure+semantic_cohesion+token_budget" for item in children)
