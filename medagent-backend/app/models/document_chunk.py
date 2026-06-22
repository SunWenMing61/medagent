# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Text（文本）、Integer（整数）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func
# 从 pgvector 的 SQLAlchemy 扩展导入 Vector 类型，用于存储向量嵌入
from pgvector.sqlalchemy import Vector

# 从应用的基础模块导入 Base（普通基类），注意此处使用 Base 而非 MySQLBase，
# 因为 document_chunk 表可能混合使用 MySQL + pgvector（PostgreSQL 扩展）
from app.db.base import Base


class DocumentChunk(Base):
    # 文档块模型，对应数据库中的 document_chunk 表，存储文档分割后的文本块及其向量嵌入
    # 设置 extend_existing=True，允许在重复定义表时覆盖而非报错（支持热重载场景）
    __table_args__ = {"extend_existing": True}
    __tablename__ = "document_chunk"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 所属文档 ID，不可为空，建有索引用于快速查询
    document_id = Column(BigInteger, nullable=False, index=True)
    # 所属知识库 ID，不可为空，建有索引用于快速查询
    kb_id = Column(BigInteger, nullable=False, index=True)
    # 块在文档内的索引顺序，默认从 0 开始
    chunk_index = Column(Integer, default=0)
    # 文本块内容，不可为空的文本字段
    content = Column(Text, nullable=False)
    # 页码（如果原文档有分页），可为空
    page_num = Column(Integer, nullable=True)
    # 向量嵌入，维度为 1024，用于语义相似度搜索，可为空
    embedding = Column(Vector(1024), nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
