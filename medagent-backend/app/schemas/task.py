"""后台任务 Pydantic 模型 —— 定义任务状态的数据结构。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskInfo(BaseModel):
    """任务信息模型，用于 API 响应序列化。"""

    task_id: str = Field(..., description="任务唯一标识")
    user_id: int = Field(..., description="发起任务的用户 ID")
    task_type: str = Field(..., description="任务类型（document_process, source_sync 等）")
    status: str = Field(..., description="任务状态：pending / processing / completed / failed")
    progress: int = Field(0, ge=0, le=100, description="进度百分比 0-100")
    total_steps: int = Field(100, description="总步骤数")
    current_step: int = Field(0, description="当前步骤")
    message: str = Field("", description="当前进度消息")
    error: Optional[str] = Field(None, description="错误信息（失败时）")
    result: Optional[Any] = Field(None, description="任务执行结果")
    created_at: str = Field(..., description="创建时间（ISO 8601）")
    updated_at: str = Field(..., description="最后更新时间（ISO 8601）")
    heartbeat_at: Optional[str] = None
    attempt: int = 0
    max_attempts: int = 1
    idempotency_key: Optional[str] = None

    class Config:
        # 允许从字典/ORM 对象创建
        from_attributes = True


class TaskCreate(BaseModel):
    """创建任务时的请求参数（服务内部使用）。"""

    task_id: str
    user_id: int
    task_type: str
    total_steps: int = 100
    message: str = ""


class TaskProgressUpdate(BaseModel):
    """进度更新请求参数（服务内部使用）。"""

    task_id: str
    current_step: int
    message: str
    status: str = "processing"
