"""后台任务管理器 —— 任务进度追踪与 WebSocket 推送。

提供统一的接口来管理异步任务的创建、进度更新和状态查询。
支持 Redis Pub/Sub 实现跨进程事件通知，方便 RQ Worker 报告进度。
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis 连接（共享，由配置管理）
_redis: Optional[Redis] = None


def _get_redis() -> Optional[Redis]:
    """获取 Redis 连接（延迟初始化）。"""
    global _redis
    if _redis is None:
        try:
            _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception as e:
            logger.warning("Failed to connect to Redis for task manager: %s", e)
            return None
    return _redis


# ── Redis key 命名空间 ──────────────────────────────────────────────────────────
TASK_PREFIX = "medagent:task:"
TASK_LIST_PREFIX = "medagent:user_tasks:"
TASK_CHANNEL = "medagent:task_events"
TASK_IDEMPOTENCY_PREFIX = "medagent:task_idempotency:"
TERMINAL_STATUSES = {"completed", "failed", "canceled"}


class TaskManager:
    """后台任务管理器，负责任务生命周期管理和进度通知。

    通过 Redis Hash 存储任务状态，通过 Pub/Sub 推送实时进度。
    即使 Redis 不可用，也通过内存 fallback 保证功能不中断。
    """

    # 内存存储（Redis fallback + 未连接 Redis 时的后备存储）
    _memory_store: Dict[str, dict] = {}
    _user_task_lists: Dict[int, List[str]] = {}
    _idempotency_store: Dict[str, str] = {}

    def _task_key(self, task_id: str) -> str:
        return f"{TASK_PREFIX}{task_id}"

    def _user_list_key(self, user_id: int) -> str:
        return f"{TASK_LIST_PREFIX}{user_id}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        """将 Redis 中的字符串数字安全地还原为 int。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _normalise_task(cls, task: dict) -> dict:
        """统一内存和 Redis 两种来源的任务字段类型。"""
        normalised = dict(task)
        for field, default in (
            ("user_id", 0),
            ("progress", 0),
            ("total_steps", 100),
            ("current_step", 0),
            ("attempt", 0),
            ("max_attempts", 1),
        ):
            normalised[field] = cls._to_int(normalised.get(field), default)

        for field in ("error", "result"):
            if normalised.get(field) == "":
                normalised[field] = None

        result = normalised.get("result")
        if isinstance(result, str) and result:
            try:
                normalised["result"] = json.loads(result)
            except (TypeError, ValueError):
                pass
        return normalised

    @staticmethod
    def _redis_mapping(task: dict) -> dict:
        """生成 Redis 可接受的映射；Redis 不允许写入 None。"""
        mapping = {}
        for key, value in task.items():
            if key == "result" and value is not None:
                mapping[key] = json.dumps(value, ensure_ascii=False, default=str)
            elif value is None:
                mapping[key] = ""
            elif isinstance(value, (dict, list, tuple)):
                mapping[key] = json.dumps(value, ensure_ascii=False, default=str)
            else:
                mapping[key] = str(value)
        return mapping

    def _store_task(self, task: dict, *, publish: bool = True) -> dict:
        """将完整任务状态同时写入 Redis 和进程内后备存储。"""
        task = self._normalise_task(task)
        task_id = task["task_id"]
        r = _get_redis()
        if r:
            try:
                r.hset(self._task_key(task_id), mapping=self._redis_mapping(task))
                r.expire(self._task_key(task_id), 86400)
            except Exception as e:
                logger.warning("Redis task store failed: %s", e)

        self._memory_store[task_id] = task
        if publish:
            self._publish_event(task_id, task)
        return task

    def start_task(
        self,
        task_id: str,
        user_id: int,
        task_type: str,
        total_steps: int = 100,
        message: str = "",
        idempotency_key: str | None = None,
        max_attempts: int = 1,
    ) -> dict:
        """注册一个新的后台任务。

        Args:
            task_id: 任务唯一标识
            user_id: 发起任务的用户 ID
            task_type: 任务类型（document_process, source_sync, entity_extraction 等）
            total_steps: 总步骤数
            message: 初始消息

        Returns:
            任务状态字典
        """
        if idempotency_key:
            existing = self.get_by_idempotency_key(idempotency_key)
            if existing and existing.get("status") not in TERMINAL_STATUSES:
                return existing

        task = {
            "task_id": task_id,
            "user_id": user_id,
            "task_type": task_type,
            "status": "pending",
            "progress": 0,
            "total_steps": total_steps,
            "current_step": 0,
            "message": message or "任务已创建",
            "error": None,
            "result": None,
            "created_at": self._now(),
            "updated_at": self._now(),
            "heartbeat_at": self._now(),
            "attempt": 0,
            "max_attempts": max(1, int(max_attempts)),
            "idempotency_key": idempotency_key,
        }

        # Redis 不接受 None，因此必须先序列化完整任务。旧实现把 error/result
        # 的 None 直接交给 hset，导致写入在 worker 进程中静默失败，API 进程
        # 随后看不到最终完成事件。
        r = _get_redis()
        if r:
            try:
                r.lpush(self._user_list_key(user_id), task_id)
                r.ltrim(self._user_list_key(user_id), 0, 99)  # 最多保留 100 条
                r.expire(self._user_list_key(user_id), 86400)
            except Exception as e:
                logger.warning("Redis task store failed: %s", e)

        # 内存后备
        if user_id not in self._user_task_lists:
            self._user_task_lists[user_id] = []
        if task_id in self._user_task_lists[user_id]:
            self._user_task_lists[user_id].remove(task_id)
        self._user_task_lists[user_id].insert(0, task_id)
        self._user_task_lists[user_id] = self._user_task_lists[user_id][:100]
        if idempotency_key:
            self._idempotency_store[idempotency_key] = task_id
            if r:
                try:
                    r.set(
                        f"{TASK_IDEMPOTENCY_PREFIX}{idempotency_key}", task_id,
                        # 只有未结束任务会在上方提前返回。终态任务需要把
                        # 幂等键更新到新任务，否则恢复线程会一直读到旧失败任务。
                        ex=86400,
                    )
                except Exception as e:
                    logger.warning("Redis idempotency store failed: %s", e)

        return self._store_task(task)

    def update_progress(
        self,
        task_id: str,
        current_step: int,
        message: str,
        status: str = "processing",
    ) -> dict:
        """更新任务进度。

        Args:
            task_id: 任务 ID
            current_step: 当前步骤（0-100）
            message: 进度消息
            status: 状态（processing / completed / failed）

        Returns:
            更新后的任务字典，如果任务不存在则返回 None
        """
        task = self.get_task(task_id)
        if not task:
            return None
        if task.get("status") in TERMINAL_STATUSES:
            return task

        # get_task 从 Redis 读取时数字是字符串。旧实现直接做 int / str，
        # 最终 complete_task 会抛 TypeError，并把任务永久留在最后一次进度
        # （常见为扫描 PDF 的 95%）。
        total_steps = max(self._to_int(task.get("total_steps"), 100), 1)
        current_step = max(self._to_int(current_step), 0)
        progress = max(0, min(int(current_step / total_steps * 100), 100))

        task["status"] = status
        task["progress"] = progress
        task["current_step"] = current_step
        task["message"] = message
        task["updated_at"] = self._now()
        task["heartbeat_at"] = task["updated_at"]

        if status == "completed":
            task["progress"] = 100
            task["current_step"] = total_steps
            task["error"] = None
        elif status == "failed":
            task["error"] = message if "error" in message.lower() else message
        return self._store_task(task)

    def begin_attempt(self, task_id: str, message: str = "任务开始执行") -> Optional[dict]:
        """Record a worker attempt without replacing the durable task identity."""

        task = self.get_task(task_id)
        if not task or task.get("status") in TERMINAL_STATUSES:
            return task
        task["attempt"] = min(
            self._to_int(task.get("attempt"), 0) + 1,
            max(self._to_int(task.get("max_attempts"), 1), 1),
        )
        task["status"] = "processing"
        task["message"] = message
        task["updated_at"] = self._now()
        task["heartbeat_at"] = task["updated_at"]
        return self._store_task(task)

    def record_attempt_failure(self, task_id: str, error: str) -> Optional[dict]:
        """Keep a failed execution attempt non-terminal so RQ can retry it."""

        task = self.get_task(task_id)
        if not task or task.get("status") in TERMINAL_STATUSES:
            return task
        attempt = self._to_int(task.get("attempt"), 0)
        maximum = max(self._to_int(task.get("max_attempts"), 1), 1)
        task["status"] = "pending"
        task["error"] = str(error)
        task["message"] = f"第 {attempt}/{maximum} 次执行失败，等待队列重试"
        task["updated_at"] = self._now()
        task["heartbeat_at"] = task["updated_at"]
        return self._store_task(task)

    def update_percent(
        self,
        task_id: str,
        progress: int,
        message: str,
        status: str = "processing",
    ) -> Optional[dict]:
        """按百分比更新任务，供页级 OCR 和块级向量化使用。"""
        task = self.get_task(task_id)
        if not task:
            return None
        if task.get("status") in TERMINAL_STATUSES:
            return task
        percent = max(0, min(self._to_int(progress), 100))
        if status != "completed":
            percent = min(percent, 99)
        task["status"] = status
        task["progress"] = 100 if status == "completed" else percent
        task["current_step"] = task["progress"]
        task["total_steps"] = 100
        task["message"] = message
        task["updated_at"] = self._now()
        task["heartbeat_at"] = task["updated_at"]
        if status == "completed":
            task["error"] = None
        elif status == "failed":
            task["error"] = message
        return self._store_task(task)

    def complete_task(
        self,
        task_id: str,
        result: Any = None,
        message: str = "任务已完成",
    ) -> dict:
        """标记任务为完成。"""
        task = self.get_task(task_id)
        if not task:
            return None
        if task.get("status") == "completed":
            return task
        task["result"] = result
        task["status"] = "completed"
        task["progress"] = 100
        task["current_step"] = max(self._to_int(task.get("total_steps"), 100), 1)
        task["message"] = message
        task["error"] = None
        task["updated_at"] = self._now()
        return self._store_task(task)

    def fail_task(self, task_id: str, error: str) -> dict:
        """标记任务为失败。"""
        task = self.get_task(task_id)
        if not task:
            return None
        if task.get("status") in TERMINAL_STATUSES:
            return task
        task["status"] = "failed"
        task["error"] = str(error)
        task["message"] = f"任务失败: {error}"
        task["updated_at"] = self._now()
        return self._store_task(task)

    def get_by_idempotency_key(self, key: str) -> Optional[dict]:
        if not key:
            return None
        task_id = None
        r = _get_redis()
        if r:
            try:
                task_id = r.get(f"{TASK_IDEMPOTENCY_PREFIX}{key}")
                if isinstance(task_id, bytes):
                    task_id = task_id.decode()
            except Exception:
                task_id = None
        task_id = task_id or self._idempotency_store.get(key)
        return self.get_task(str(task_id)) if task_id else None

    def get_task(self, task_id: str) -> Optional[dict]:
        """获取任务状态。"""
        if not task_id:
            return None

        # 尝试 Redis
        r = _get_redis()
        if r:
            try:
                data = r.hgetall(self._task_key(task_id))
                if data:
                    task = {
                        k.decode() if isinstance(k, bytes) else k:
                            v.decode() if isinstance(v, bytes) else v
                        for k, v in data.items()
                    }
                    return self._normalise_task(task)
            except Exception:
                pass

        # 后备：内存
        task = self._memory_store.get(task_id)
        return self._normalise_task(task) if task else None

    def get_user_tasks(self, user_id: int, limit: int = 20) -> List[dict]:
        """获取用户最近的 task 列表。"""
        tasks = []
        r = _get_redis()

        if r:
            try:
                task_ids = r.lrange(self._user_list_key(user_id), 0, limit - 1)
                for tid in task_ids:
                    tid = tid.decode() if isinstance(tid, bytes) else tid
                    task = self.get_task(tid)
                    if task:
                        tasks.append(task)
                return self._fail_stale_tasks(tasks)
            except Exception:
                pass

        # 后备：内存
        task_ids = self._user_task_lists.get(user_id, [])[:limit]
        for tid in task_ids:
            task = self._memory_store.get(tid)
            if task:
                tasks.append(task)
        return self._fail_stale_tasks(tasks)

    def _fail_stale_tasks(self, tasks: List[dict]) -> List[dict]:
        """把 worker 已消失且长期无进度的 processing 任务收敛到 failed。

        RQ 的硬退出、主机断电等场景可能来不及执行失败回调。只处理 processing，
        不处理仍在排队的 pending，避免队列积压时误报失败。
        """
        now = datetime.now(timezone.utc)
        stale_after = max(settings.TASK_STALE_AFTER_SECONDS, 60)
        reconciled = []
        for task in tasks:
            if task.get("status") == "processing":
                try:
                    updated_at = datetime.fromisoformat(
                        str(task.get("updated_at", "")).replace("Z", "+00:00")
                    )
                    if updated_at.tzinfo is None:
                        updated_at = updated_at.replace(tzinfo=timezone.utc)
                    if (now - updated_at).total_seconds() > stale_after:
                        task = self.fail_task(
                            task["task_id"],
                            f"任务超过 {stale_after} 秒没有进度，worker 可能已退出",
                        ) or task
                except (TypeError, ValueError):
                    logger.warning("Invalid task updated_at: %r", task.get("updated_at"))
            reconciled.append(task)
        return reconciled

    def delete_task(self, task_id: str) -> bool:
        """删除任务记录。"""
        r = _get_redis()
        if r:
            try:
                r.delete(self._task_key(task_id))
            except Exception:
                pass

        self._memory_store.pop(task_id, None)

        # 从用户列表中移除
        for uid in list(self._user_task_lists.keys()):
            if task_id in self._user_task_lists[uid]:
                self._user_task_lists[uid] = [t for t in self._user_task_lists[uid] if t != task_id]
        return True

    def _publish_event(self, task_id: str, task: dict):
        """通过 Redis Pub/Sub 发布任务事件。"""
        r = _get_redis()
        if not r:
            return
        try:
            event = {
                "type": "task_progress",
                "task_id": task_id,
                "status": task.get("status"),
                "progress": task.get("progress"),
                "message": task.get("message"),
                "updated_at": task.get("updated_at"),
            }
            r.publish(TASK_CHANNEL, json.dumps(event))
        except Exception as e:
            logger.debug("Redis pub failed: %s", e)


# 全局单例实例，与其他 service 风格一致
task_manager = TaskManager()
