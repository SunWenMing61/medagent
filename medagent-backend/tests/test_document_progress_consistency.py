"""Document status/progress consistency regression tests."""

from types import SimpleNamespace
from unittest.mock import patch

from app.api.v1.documents import _document_progress


def _document(**overrides):
    values = {
        "processing_task_id": "doc-106",
        "parse_status": "success",
        "vector_status": "pending",
        "error_message": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_vector_success_overrides_stale_failed_task_message():
    doc = _document(vector_status="success")
    stale_task = {"status": "failed", "progress": 92, "message": "任务失败: SSL EOF"}

    with patch("app.api.v1.documents.task_manager.get_task", return_value=stale_task):
        assert _document_progress(doc) == (100, "处理完成")


def test_vector_failure_cannot_be_presented_as_completed_parse():
    doc = _document(vector_status="failed", error_message="Embedding network failure")
    failed_task = {"status": "failed", "progress": 92, "message": "任务失败"}

    with patch("app.api.v1.documents.task_manager.get_task", return_value=failed_task):
        assert _document_progress(doc) == (92, "Embedding network failure")
