"""任务进度跨 Redis 进程边界的回归测试。"""

import uuid
from unittest.mock import patch

import pytest

from app.services.task_manager import TaskManager
from app.tasks.document_tasks import enqueue_document


class FakeRedis:
    def __init__(self):
        self.hashes = {}
        self.lists = {}
        self.events = []

    def hset(self, key, mapping):
        assert all(value is not None for value in mapping.values())
        self.hashes[key] = dict(mapping)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def expire(self, key, ttl):
        return True

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        self.lists[key] = self.lists.get(key, [])[start : end + 1]

    def lrange(self, key, start, end):
        return self.lists.get(key, [])[start : end + 1]

    def publish(self, channel, value):
        self.events.append((channel, value))


def test_completion_after_redis_round_trip_does_not_stick_at_95():
    redis = FakeRedis()
    manager = TaskManager()
    manager._memory_store = {}
    manager._user_task_lists = {}

    with patch("app.services.task_manager._get_redis", return_value=redis):
        manager.start_task("scan-1", 7, "document_process", total_steps=100)
        manager.update_percent("scan-1", 95, "OCR 252/265")

        # 强制下一次读取走 Redis，复现 API/worker 两个不同进程的真实场景。
        manager._memory_store = {}
        completed = manager.complete_task(
            "scan-1", result={"chunks": 12}, message="处理完成"
        )

        assert completed["status"] == "completed"
        assert completed["progress"] == 100
        assert completed["result"] == {"chunks": 12}
        assert manager.get_task("scan-1")["user_id"] == 7


def test_failure_keeps_last_progress_but_changes_terminal_state():
    redis = FakeRedis()
    manager = TaskManager()
    manager._memory_store = {}
    manager._user_task_lists = {}

    with patch("app.services.task_manager._get_redis", return_value=redis):
        manager.start_task("scan-2", 8, "document_process", total_steps=100)
        manager.update_percent("scan-2", 95, "OCR 252/265")
        failed = manager.fail_task("scan-2", "JobTimeoutException")

        assert failed["status"] == "failed"
        assert failed["progress"] == 95
        assert "JobTimeoutException" in failed["error"]


def test_execution_failure_stays_retryable_until_terminal_callback():
    redis = FakeRedis()
    manager = TaskManager()
    manager._memory_store = {}
    manager._user_task_lists = {}

    with patch("app.services.task_manager._get_redis", return_value=redis):
        manager.start_task("scan-retry", 9, "document_process", max_attempts=3)
        started = manager.begin_attempt("scan-retry", "开始处理文档")
        retrying = manager.record_attempt_failure("scan-retry", "temporary provider error")

        assert started["attempt"] == 1
        assert retrying["status"] == "pending"
        assert retrying["attempt"] == 1
        assert retrying["max_attempts"] == 3
        assert "等待队列重试" in retrying["message"]

        # A later execution can still advance the same task; only fail_task is terminal.
        manager.begin_attempt("scan-retry", "重试文档处理")
        progressed = manager.update_percent("scan-retry", 40, "OCR 2/5")
        assert progressed["status"] == "processing"
        assert progressed["attempt"] == 2


def test_enqueue_failure_keeps_document_pending_for_outbox_retry():
    idempotency_key = "document.process:42:hash"
    suffix = uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:12]
    task = {"task_id": f"doc_42_{suffix}", "status": "pending"}
    with (
        patch("app.tasks.document_tasks.task_manager.get_by_idempotency_key", return_value=None),
        patch("app.tasks.document_tasks.task_manager.start_task", return_value=task),
        patch("app.tasks.document_tasks._rq_job_is_active", return_value=False),
        patch("app.tasks.document_tasks._rq_workers_available", return_value=False),
        patch("app.tasks.document_tasks.settings.DOCUMENT_INLINE_FALLBACK_ENABLED", False),
        patch("app.tasks.document_tasks.task_manager.fail_task"),
        patch("app.tasks.document_tasks.doc_queue.enqueue", side_effect=ConnectionError("redis down")),
        patch("app.tasks.document_tasks._mark_document_dispatch_pending") as mark_pending,
        patch("app.tasks.document_tasks._mark_document_failed") as mark_failed,
    ):
        with pytest.raises(ConnectionError, match="redis down"):
            enqueue_document(42, 7, idempotency_key=idempotency_key)

    mark_pending.assert_called_once_with(42, "redis down")
    mark_failed.assert_not_called()


def test_enqueue_without_rq_worker_uses_automatic_local_vectorization():
    idempotency_key = "document.process:43:hash"
    suffix = uuid.uuid5(uuid.NAMESPACE_URL, idempotency_key).hex[:12]
    task_id = f"doc_43_{suffix}"
    task = {"task_id": task_id, "status": "pending"}
    with (
        patch("app.tasks.document_tasks.task_manager.get_by_idempotency_key", return_value=None),
        patch("app.tasks.document_tasks.task_manager.start_task", return_value=task),
        patch("app.tasks.document_tasks._rq_job_is_active", return_value=False),
        patch("app.tasks.document_tasks._rq_workers_available", return_value=False),
        patch("app.tasks.document_tasks.settings.DOCUMENT_INLINE_FALLBACK_ENABLED", True),
        patch("app.tasks.document_tasks._schedule_local_document") as schedule_local,
        patch("app.tasks.document_tasks.doc_queue.enqueue") as enqueue_rq,
    ):
        result = enqueue_document(43, 7, idempotency_key=idempotency_key)

    assert result == task_id
    schedule_local.assert_called_once_with(43, task_id, False)
    enqueue_rq.assert_not_called()
