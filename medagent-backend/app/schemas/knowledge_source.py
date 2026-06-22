# 从 pydantic 导入 BaseModel（数据模型基类）和 Field（字段验证与元数据）
from pydantic import BaseModel, Field
# 从 Python 标准库导入 datetime，用于时间戳字段类型
from datetime import datetime
# 从 typing 导入 Optional（可选类型）、Any（任意类型）
from typing import Optional, Any


class SourceCreateRequest(BaseModel):
    # 创建数据源请求模型，用于新增外部知识数据源
    # 所属知识库 ID，必填
    kb_id: int = Field(..., description="Knowledge base ID")
    # 数据源类型，必填，如 pubmed（PubMed 文献）、msd_manual（默沙东诊疗手册）、drug_label（药品说明书）
    source_type: str = Field(..., description="Source type: pubmed, msd_manual, drug_label")
    # 数据源显示名称，必填，长度 1~255
    name: str = Field(..., min_length=1, max_length=255, description="Display name")
    # 适配器专属配置，默认为空字典
    config: dict = Field(default_factory=dict, description="Adapter-specific configuration")


class SourceUpdateRequest(BaseModel):
    # 更新数据源请求模型，所有字段均为可选
    # 数据源显示名称，可选，最大长度 255
    name: Optional[str] = Field(None, max_length=255)
    # 适配器配置，可选字典
    config: Optional[dict] = None
    # 新的关联知识库 ID，可选，用于转移数据源所属关系
    kb_id: Optional[int] = Field(None, description="New knowledge base ID to associate with")


class SourceResponse(BaseModel):
    # 数据源响应模型，返回数据源的完整信息
    # 数据源 ID
    id: int
    # 所属知识库 ID
    kb_id: int
    # 数据源类型
    source_type: str
    # 数据源名称
    name: str
    # 配置信息（JSON 字符串形式）
    config: str
    # 同步状态：idle（空闲）、syncing（同步中）、success（成功）、failed（失败）
    sync_status: str
    # 文档数量，默认值为 0
    document_count: int = 0
    # 最后同步时间，可为空
    last_sync_at: Optional[datetime] = None
    # 错误信息，可为空
    error_message: Optional[str] = None
    # 创建时间，可为空
    created_at: Optional[datetime] = None
    # 更新时间，可为空
    updated_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True


class SourceStatusResponse(BaseModel):
    # 数据源状态响应模型，返回同步状态简要信息
    # 数据源 ID
    id: int
    # 同步状态
    sync_status: str
    # 最后同步时间，可为空
    last_sync_at: Optional[datetime] = None
    # 错误信息，可为空
    error_message: Optional[str] = None


class SourceSyncResponse(BaseModel):
    # 数据源同步操作响应模型，返回启动同步的结果
    # 数据源 ID
    source_id: int
    # 同步状态，默认值为 "syncing"（同步中）
    sync_status: str = "syncing"
    # 提示消息，默认为中文 "同步已启动"
    message: str = "同步已启动"


class SourceSchemaResponse(BaseModel):
    # 数据源配置模式响应模型，描述某个数据源类型的配置结构
    # 数据源类型标识
    source_type: str
    # 数据源显示名称（人类可读）
    display_name: str
    # 配置字段的模式定义（JSON Schema 格式）
    config_schema: dict
    # 配置的默认值
    defaults: dict

    class Config:
        # 配置允许通过字段名称（而非别名）来创建模型实例
        populate_by_name = True
        # schema_extra / json_schema_extra is not needed; "schema" is fine in JSON
