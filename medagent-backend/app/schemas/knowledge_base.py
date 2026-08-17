# 从 pydantic 导入 BaseModel（数据模型基类）和 Field（字段验证与元数据）
from pydantic import BaseModel, Field
# 从 Python 标准库导入 datetime，用于时间戳字段类型
from datetime import datetime
# 从 typing 导入 Optional（可选类型）
from typing import Optional


class KBCreateRequest(BaseModel):
    # 创建知识库请求模型，用于新建知识库时的请求体验证
    # 知识库名称，必填，长度限制 1~255 字符
    name: str = Field(..., min_length=1, max_length=255)
    # 知识库描述，可选
    description: Optional[str] = None
    # 知识库类型，默认值为 "general"，必须匹配正则：general（通用）、drug（药品）、paper（论文）
    type: str = Field(default="general", pattern=r"^(general|drug|paper)$")
    # 可见性，默认值为 "private"，必须匹配正则：private（私有）、public（公开）
    visibility: str = Field(default="private", pattern=r"^(private|public)$")


class KBUpdateRequest(BaseModel):
    # 更新知识库请求模型，所有字段均为可选，只更新传入的字段
    # 知识库名称，可选
    name: Optional[str] = None
    # 知识库描述，可选
    description: Optional[str] = None
    # 知识库类型，可选
    type: Optional[str] = None
    # 可见性，可选
    visibility: Optional[str] = None


class KBResponse(BaseModel):
    # 知识库信息响应模型，返回知识库的完整信息
    # 知识库 ID
    id: int
    # 知识库名称
    name: str
    # 知识库描述，可为空
    description: Optional[str] = None
    # 知识库类型
    type: str
    # 所有者用户 ID
    owner_id: int
    # 可见性
    visibility: str
    # 状态（1=正常，0=禁用）
    status: int
    # 创建时间，可为空
    created_at: Optional[datetime] = None
    # 更新时间，可为空
    updated_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True
