"""后台任务 API 路由 —— 查询和管理异步任务状态。

提供 REST API 用于获取任务列表、查看任务详情、删除任务记录。
WebSocket 实时推送端点已移至 app/api/v1/ws.py，在 main.py 中直接挂载。
"""

import logging
import re
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, rate_limit
from app.db.session import get_mysql_db
from app.models.user import User
from app.schemas.task import TaskInfo
from app.services.task_manager import task_manager
from app.models.document import Document
from app.tasks.document_tasks import enqueue_document

logger = logging.getLogger(__name__)

router = APIRouter()
_DOCUMENT_TASK_ID = re.compile(r"^doc_(\d+)_")


# ── REST API ─────────────────────────────────────────────────────────────────────


@router.get("/tasks", response_model=List[TaskInfo])
def list_tasks(
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
):
    """获取当前用户的所有后台任务列表。

    Args:
        limit: 返回任务数量上限，默认 20，最大 100

    Returns:
        TaskInfo 列表，按创建时间倒序排列
    """
    tasks = task_manager.get_user_tasks(current_user.id, limit=limit)
    # 将 bytes 值转为字符串（Redis 存储可能返回 bytes）
    cleaned = []
    for t in tasks:
        cleaned.append({k: v.decode() if isinstance(v, bytes) else v for k, v in t.items()})
    return cleaned


@router.get("/tasks/{task_id}", response_model=TaskInfo)
def get_task(
    task_id: str,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """获取指定任务的详细状态。

    Args:
        task_id: 任务唯一标识

    Returns:
        TaskInfo 任务状态详情

    Raises:
        404: 任务不存在
        403: 无权访问其他用户的任务
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 权限检查：只能查看自己的任务，管理员可以查看所有
    uid = task.get("user_id")
    if isinstance(uid, bytes):
        uid = int(uid.decode())
    if uid != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权访问该任务")
    return task


@router.delete("/tasks/{task_id}")
def delete_task(
    task_id: str,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """删除已完成或失败的任务记录。

    只能删除自己发起的任务，管理员可以删除任意任务。

    Args:
        task_id: 任务唯一标识

    Returns:
        {"message": "Task deleted"}

    Raises:
        404: 任务不存在
        403: 无权删除其他用户的任务
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    # 权限检查
    uid = task.get("user_id")
    if isinstance(uid, bytes):
        uid = int(uid.decode())
    if uid != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权删除该任务")

    task_manager.delete_task(task_id)
    return {"message": "任务已删除"}


@router.post("/tasks/{task_id}/retry", response_model=TaskInfo)
def retry_task(
    task_id: str,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.get("user_id") != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权重试该任务")
    if task.get("status") != "failed":
        raise HTTPException(status_code=409, detail="仅失败任务可以重试")
    match = _DOCUMENT_TASK_ID.match(task_id)
    if not match:
        raise HTTPException(status_code=400, detail="该任务类型暂不支持重试")
    document = db.query(Document).filter(Document.id == int(match.group(1))).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    if document.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="无权重试该文档")
    new_task_id = enqueue_document(
        document.id,
        document.uploader_id,
        idempotency_key=f"document.retry:{document.id}:{uuid.uuid4().hex}",
    )
    return task_manager.get_task(new_task_id)
