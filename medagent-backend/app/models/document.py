# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Integer（整数）、DateTime（日期时间）、Text（文本）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, JSON, func

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class Document(MySQLBase):
    # 文档模型，对应数据库中的 document 表，用于管理上传或同步的知识文档
    __tablename__ = "document"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 所属知识库 ID，不可为空，建有索引用于快速查询
    kb_id = Column(BigInteger, nullable=False, index=True)
    # 文件名，不可为空，最大长度 255 字符
    filename = Column(String(255), nullable=False)
    # 文件类型，不可为空，例如 pdf、docx、txt、md 等
    file_type = Column(String(20), nullable=False)
    # 文件大小（字节），默认值为 0
    file_size = Column(BigInteger, default=0)
    # 文件存储路径，可为空
    file_path = Column(String(500), nullable=True)
    # 来源 URL，最大长度 1024，可为空
    source_url = Column(String(1024), nullable=True)
    # 解析状态，默认值为 "pending"，可选：pending（待处理）、processing（处理中）、success（成功）、failed（失败）
    parse_status = Column(String(20), default="pending")  # pending, processing, success, failed
    # 向量化状态，默认值为 "pending"，可选：pending（待处理）、processing（处理中）、success（成功）、failed（失败）
    vector_status = Column(String(20), default="pending")  # pending, processing, success, failed
    # 上传者用户 ID，不可为空
    uploader_id = Column(BigInteger, nullable=False)
    # 错误信息，解析或向量化失败时记录详细原因
    error_message = Column(Text, nullable=True)
    content_sha256 = Column(String(64), nullable=True, index=True)
    normalized_text_sha256 = Column(String(64), nullable=True, index=True)
    cleaning_version = Column(String(64), nullable=True)
    quality_status = Column(String(32), nullable=False, default="pending", index=True)
    document_version = Column(String(64), nullable=True)
    version_status = Column(String(20), nullable=False, default="active", index=True)
    supersedes_document_id = Column(BigInteger, nullable=True, index=True)
    parser_version = Column(String(64), nullable=True)
    chunker_version = Column(String(64), nullable=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_dimensions = Column(Integer, nullable=True)
    page_count = Column(Integer, nullable=False, default=0)
    ocr_page_count = Column(Integer, nullable=False, default=0)
    chunk_count = Column(Integer, nullable=False, default=0)
    processing_warnings = Column(JSON, nullable=True)
    processing_task_id = Column(String(100), nullable=True, index=True)
    processing_started_at = Column(DateTime, nullable=True)
    processing_completed_at = Column(DateTime, nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
    # 更新时间，默认使用 now()，并在更新时自动刷新
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
