# 从 pydantic 导入 BaseModel（数据模型基类）和 Field（字段验证与元数据）
from pydantic import BaseModel, Field
# 从 Python 标准库导入 datetime，用于时间戳字段类型
from datetime import datetime
# 从 typing 导入 Optional（可选类型）
from typing import Any, Optional


class FeedbackRequest(BaseModel):
    # 用户反馈请求模型，用于提交用户对 AI 回答的评价
    # 被反馈的消息 ID，必填整数
    message_id: int
    # 反馈类型，必填，必须匹配正则：like（点赞）、dislike（点踩）、none（无）
    feedback_type: str = Field(..., pattern=r"^(like|dislike|none)$")
    # 用户附加评论，可选文本
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    # 用户反馈响应模型，返回已保存的反馈记录
    # 反馈记录 ID
    id: int
    # 反馈用户 ID
    user_id: int
    # 被反馈的消息 ID
    message_id: int
    # 反馈类型
    feedback_type: str
    # 用户附加评论，可为空
    comment: Optional[str] = None
    # 创建时间，可为空
    created_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True


class AnswerPreferenceRequest(BaseModel):
    message_id: int = Field(gt=0)
    chosen_variant_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class AnswerPreferenceResponse(BaseModel):
    message_id: int
    chosen_variant_id: str
    changed: bool
    profile: dict[str, Any]
