# 从 pydantic 导入 BaseModel（数据模型基类）和 Field（字段验证与元数据）
from pydantic import BaseModel, Field
# 从 Python 标准库导入 datetime，用于时间戳字段类型
from datetime import datetime
# 从 typing 导入 Optional（可选类型）、List（列表类型）、Any（任意类型）
from typing import Optional, List, Any, Literal


class AskRequest(BaseModel):
    # 提问请求模型，用于会话中向 AI 发送消息的请求体验证
    # 问题内容，必填，最小长度 1 字符
    question: str = Field(..., min_length=1)
    # 可选的知识库 ID 列表，用于限定搜索范围
    kb_ids: Optional[List[int]] = None
    # 可选的会话 ID，如果不提供则创建新会话
    session_id: Optional[int] = None
    assistant_profile: Literal["general_qa", "memory_qa"] = "memory_qa"


class AskResponse(BaseModel):
    # 提问响应模型，AI 回答问题后的返回数据结构
    # 会话 ID（新建或已有的会话）
    session_id: int
    # 用户原始问题
    question: str
    # AI 生成的回答内容
    answer: str
    # 可选的引用来源列表，每个元素为一个字典（文档/块信息）
    references: Optional[List[dict]] = None
    # 可选的安全标记，标识回答是否触发安全策略
    safety_flag: Optional[str] = None
    # 可选的免责声明文本
    disclaimer: Optional[str] = None
    assistant_profile: str = "memory_qa"
    cache_hit: bool = False
    cache_age_seconds: Optional[float] = None
    cache_lookup_latency_ms: Optional[float] = None
    answer_variants: List[dict] = Field(default_factory=list)
    recommended_variant_id: Optional[str] = None
    message_id: Optional[int] = None


class SessionResponse(BaseModel):
    # 会话概要响应模型，用于返回会话列表中的单个会话信息
    # 会话 ID
    id: int
    # 所属用户 ID
    user_id: int
    # 会话标题，可为空
    title: Optional[str] = None
    # 会话类型，如 qa、health、drug、paper
    session_type: str
    # 会话摘要，可为空
    summary: Optional[str] = None
    # 创建时间，可为空
    created_at: Optional[datetime] = None
    # 更新时间，可为空
    updated_at: Optional[datetime] = None
    # 关联的知识库 ID 列表，可为空
    kb_ids: Optional[List[int]] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True


class MessageResponse(BaseModel):
    # 消息响应模型，用于返回会话中的单条消息记录
    # 消息 ID
    id: int
    # 所属会话 ID
    session_id: int
    # 消息角色：user（用户）或 assistant（助手/AI）
    role: str
    # 消息文本内容
    content: str
    # 引用来源的 JSON 数据，可为任意类型
    references_json: Optional[Any] = None
    # 安全标记，可为空
    safety_flag: Optional[str] = None
    answer_variants_json: Optional[List[dict]] = None
    recommended_variant_id: Optional[str] = None
    selected_variant_id: Optional[str] = None
    # 创建时间，可为空
    created_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True


class SessionDetailResponse(BaseModel):
    # 会话详情响应模型，包含会话信息和全部消息列表
    # 会话概要信息
    session: SessionResponse
    # 会话包含的所有消息列表
    messages: List[MessageResponse]
