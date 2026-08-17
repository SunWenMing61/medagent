"""Regression tests for PDF parse checkpoints and pipeline retry boundaries."""

import hashlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.document_processing_service import DocumentProcessingService
from app.services.embedding_service import EmbeddingTransientError
from app.tasks.document_tasks import _run_document_locally


def _query_result(rows):
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.all.return_value = rows
    return query


def _checkpoint_fixture():
    text = "第一页清洗文本\n\n第二页清洗文本"
    document = SimpleNamespace(
        id=104,
        file_path="sample.pdf",
        file_type="pdf",
        parser_version="parser-v1",
        cleaning_version="clean-v1",
        content_sha256="source-hash",
        normalized_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        processing_warnings=["warning"],
    )
    pages = [
        SimpleNamespace(
            page_num=1, cleaned_text="第一页清洗文本", raw_text="第一页原文",
            extraction_method="ocr", ocr_confidence=0.91, width=100.0, height=200.0,
            warnings_json=[], quality_score=None, quality_status="not_evaluated",
            metadata_json=None,
        ),
        SimpleNamespace(
            page_num=2, cleaned_text="第二页清洗文本", raw_text="第二页原文",
            extraction_method="native", ocr_confidence=None, width=100.0, height=200.0,
            warnings_json=[], quality_score=None, quality_status="not_evaluated",
            metadata_json=None,
        ),
    ]
    blocks = [SimpleNamespace(
        id=1, page_num=1, text="第一页清洗文本", block_type="text",
        bbox_json=None, reading_order=0, metadata_json=None,
        block_id="p1_b0", extraction_method="ocr",
    )]
    return document, pages, blocks


def test_complete_clean_text_checkpoint_restores_without_opening_pdf():
    document, pages, blocks = _checkpoint_fixture()
    db = MagicMock()
    db.query.side_effect = [_query_result(pages), _query_result(blocks)]

    parsed = DocumentProcessingService().load_parsed_checkpoint(db, document)

    assert parsed is not None
    assert parsed.text == "第一页清洗文本\n\n第二页清洗文本"
    assert parsed.page_count == 2
    assert parsed.pages[0].blocks[0].block_id == "p1_b0"
    assert parsed.metadata["content_sha256"] == "source-hash"


def test_incomplete_clean_text_checkpoint_is_rejected():
    document, pages, blocks = _checkpoint_fixture()
    document.normalized_text_sha256 = "0" * 64
    db = MagicMock()
    db.query.side_effect = [_query_result(pages), _query_result(blocks)]

    assert DocumentProcessingService().load_parsed_checkpoint(db, document) is None


def test_local_executor_never_retries_the_whole_pdf_pipeline():
    lock_db = MagicMock()
    lock_db.execute.return_value.scalar.return_value = 1
    with (
        patch("app.tasks.document_tasks.MySQLSessionLocal", return_value=lock_db),
        patch("app.tasks.document_tasks.process_document", side_effect=RuntimeError("embedding HTTP 400")) as process,
        patch("app.tasks.document_tasks.task_manager.fail_task") as fail_task,
        patch("app.tasks.document_tasks._mark_document_failed") as mark_failed,
    ):
        with pytest.raises(RuntimeError, match="文档自动处理失败"):
            _run_document_locally(104, "doc-104")

    process.assert_called_once_with(104, "doc-104", force_reparse=False)
    fail_task.assert_called_once()
    mark_failed.assert_called_once()


def test_local_executor_retries_transient_embedding_failure_from_checkpoint():
    lock_db = MagicMock()
    lock_db.execute.return_value.scalar.return_value = 1
    with (
        patch("app.tasks.document_tasks.MySQLSessionLocal", return_value=lock_db),
        patch(
            "app.tasks.document_tasks.process_document",
            side_effect=[
                EmbeddingTransientError("SSL EOF"),
                {"status": "success", "document_id": 106},
            ],
        ) as process,
        patch("app.tasks.document_tasks.task_manager.record_attempt_failure") as record_failure,
        patch("app.tasks.document_tasks.task_manager.fail_task") as fail_task,
        patch("app.tasks.document_tasks._mark_document_failed") as mark_failed,
        patch("app.tasks.document_tasks.time.sleep") as sleep,
        patch("app.tasks.document_tasks.settings.DOCUMENT_PROCESS_MAX_ATTEMPTS", 3),
        patch("app.tasks.document_tasks.settings.DOCUMENT_RETRY_DELAY_SECONDS", 5),
    ):
        result = _run_document_locally(106, "doc-106")

    assert result["status"] == "success"
    assert process.call_count == 2
    process.assert_called_with(106, "doc-106", force_reparse=False)
    record_failure.assert_called_once_with("doc-106", "SSL EOF")
    sleep.assert_called_once_with(5.0)
    fail_task.assert_not_called()
    mark_failed.assert_not_called()


def test_forced_rebuild_retries_embedding_from_new_checkpoint_only():
    lock_db = MagicMock()
    lock_db.execute.return_value.scalar.return_value = 1
    with (
        patch("app.tasks.document_tasks.MySQLSessionLocal", return_value=lock_db),
        patch(
            "app.tasks.document_tasks.process_document",
            side_effect=[EmbeddingTransientError("SSL EOF"), {"status": "success"}],
        ) as process,
        patch("app.tasks.document_tasks.task_manager.record_attempt_failure"),
        patch("app.tasks.document_tasks.time.sleep"),
        patch("app.tasks.document_tasks.settings.DOCUMENT_PROCESS_MAX_ATTEMPTS", 2),
        patch("app.tasks.document_tasks.settings.DOCUMENT_RETRY_DELAY_SECONDS", 0),
    ):
        _run_document_locally(106, "doc-106-rebuild", force_reparse=True)

    assert process.call_args_list[0].kwargs["force_reparse"] is True
    assert process.call_args_list[1].kwargs["force_reparse"] is False
