# 从 pydantic 导入 BaseModel（数据模型基类）
from pydantic import BaseModel, ConfigDict
# 从 Python 标准库导入 datetime，用于时间戳字段类型
from datetime import datetime
# 从 typing 导入 Optional（可选类型）
from typing import Optional


class DocumentResponse(BaseModel):
    # 文档信息响应模型，返回文档的详细属性
    # 文档 ID
    id: int
    # 所属知识库 ID
    kb_id: int
    # 文件名
    filename: str
    # 文件类型（如 pdf、docx、txt 等）
    file_type: str
    # 文件大小（字节）
    file_size: int
    # 解析状态：pending、processing、success、failed
    parse_status: str
    # 向量化状态：pending、processing、success、failed
    vector_status: str
    # 上传者用户 ID
    uploader_id: int
    # 来源 URL，可为空
    source_url: Optional[str] = None
    # 错误信息，解析或向量化失败时记录，可为空
    error_message: Optional[str] = None
    cleaning_version: Optional[str] = None
    quality_status: Optional[str] = None
    processing_task_id: Optional[str] = None
    processing_progress: int = 0
    processing_message: Optional[str] = None
    # 创建时间，可为空
    created_at: Optional[datetime] = None
    # 更新时间，可为空
    updated_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True


class DocumentPreviewResponse(BaseModel):
    # 文档预览响应模型，返回文档内容预览
    # 文件名
    filename: str
    # 文件类型
    file_type: str
    # 文档文本内容
    content: str
    # 文档总长度（字符数）
    total_length: int


class DocumentStatusResponse(BaseModel):
    # 文档状态响应模型，返回文档的解析和向量化状态
    # 文档 ID
    id: int
    # 解析状态
    parse_status: str
    # 向量化状态
    vector_status: str
    # 错误信息，可为空
    error_message: Optional[str] = None
    processing_task_id: Optional[str] = None
    processing_progress: int = 0
    processing_message: Optional[str] = None


class VectorStoreRebuildResponse(BaseModel):
    kb_id: int
    scheduled: int
    skipped_active: int
    document_ids: list[int]
    message: str


class DocumentQualityDetailResponse(BaseModel):
    document_id: int
    cleaning_version: Optional[str] = None
    quality_status: str
    report: dict
    pages: list[dict]
    raw_blocks: list[dict]
    clean_blocks: list[dict]
    tables: list[dict]
    cleaning_actions: list[dict]


class DocumentQualityReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str
    comment: Optional[str] = None
