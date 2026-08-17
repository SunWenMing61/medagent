# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Text（文本）、Integer（整数）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Text, Integer, Float, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
# 从 pgvector 的 SQLAlchemy 扩展导入 Vector 类型，用于存储向量嵌入
from pgvector.sqlalchemy import Vector

# 从应用的基础模块导入 Base（普通基类），注意此处使用 Base 而非 MySQLBase，
# 因为 document_chunk 表可能混合使用 MySQL + pgvector（PostgreSQL 扩展）
from app.db.base import Base


class DocumentChunk(Base):
    # 文档块模型，对应数据库中的 document_chunk 表，存储文档分割后的文本块及其向量嵌入
    # 设置 extend_existing=True，允许在重复定义表时覆盖而非报错（支持热重载场景）
    __table_args__ = (
        UniqueConstraint("document_id", "logical_id", name="uq_document_chunk_document_logical"),
        {"extend_existing": True},
    )
    __tablename__ = "document_chunk"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # Keep the tenant boundary in PostgreSQL so authorization is enforced before ranking.
    tenant_id = Column(BigInteger, nullable=False, default=1, index=True)
    # 所属文档 ID，不可为空，建有索引用于快速查询
    document_id = Column(BigInteger, nullable=False, index=True)
    # 所属知识库 ID，不可为空，建有索引用于快速查询
    kb_id = Column(BigInteger, nullable=False, index=True)
    # 块在文档内的索引顺序，默认从 0 开始
    chunk_index = Column(Integer, default=0)
    # 文本块内容，不可为空的文本字段
    content = Column(Text, nullable=False)
    title = Column(String(500), nullable=True)
    section_title = Column(String(500), nullable=True)
    # 页码（如果原文档有分页），可为空
    page_num = Column(Integer, nullable=True)
    # Logical IDs are deterministic within a document. Identical source files may
    # legitimately be uploaded to different knowledge bases/documents.
    logical_id = Column(String(64), nullable=True, index=True)
    parent_chunk_id = Column(BigInteger, ForeignKey("document_chunk.id", ondelete="CASCADE"), nullable=True, index=True)
    chunk_type = Column(String(16), nullable=False, default="child", index=True)
    page_start = Column(Integer, nullable=True)
    page_end = Column(Integer, nullable=True)
    section_path = Column(JSONB, nullable=True)
    start_offset = Column(Integer, nullable=True)
    end_offset = Column(Integer, nullable=True)
    token_count = Column(Integer, nullable=False, default=0)
    content_sha256 = Column(String(64), nullable=True, index=True)
    parser_version = Column(String(64), nullable=True)
    chunker_version = Column(String(64), nullable=True)
    embedding_model = Column(String(128), nullable=True)
    embedding_dimensions = Column(Integer, nullable=True)
    embedding_version = Column(String(64), nullable=True, index=True)
    embedded_at = Column(DateTime, nullable=True)
    metadata_json = Column(JSONB, nullable=True)
    medical_entities = Column(JSONB, nullable=True)
    normalized_drug_names = Column(JSONB, nullable=True)
    disease_names = Column(JSONB, nullable=True)
    medical_codes = Column(JSONB, nullable=True)
    keywords = Column(JSONB, nullable=True)
    source_type = Column(String(32), nullable=False, default="local_knowledge_base", index=True)
    authority_level = Column(Integer, nullable=False, default=7, index=True)
    document_version = Column(String(64), nullable=True, index=True)
    publication_date = Column(DateTime, nullable=True, index=True)
    source_block_ids = Column(JSONB, nullable=True)
    content_type = Column(String(24), nullable=False, default="paragraph", index=True)
    cleaning_version = Column(String(64), nullable=True)
    extraction_method = Column(String(32), nullable=True)
    ocr_confidence = Column(Float, nullable=True)
    quality_status = Column(String(32), nullable=False, default="good", index=True)
    search_vector = Column(TSVECTOR, nullable=True)
    embedding = Column(Vector(), nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
