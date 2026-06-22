# 从 SQLAlchemy 的 ORM 模块导入 DeclarativeBase 基类
# DeclarativeBase 是 SQLAlchemy 2.0 中定义 ORM 模型的推荐方式
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    PostgreSQL 模型的声明式基类。

    所有 PostgreSQL 数据库模型（主要是支持 pgvector 的 document_chunk 表）
    都应该继承此类。PostgreSQL 主要用于存储文档的向量嵌入，
    以支持语义相似度搜索。
    """
    pass  # 无需额外功能，直接继承 DeclarativeBase 即可


class MySQLBase(DeclarativeBase):
    """
    MySQL 模型的声明式基类。

    所有 MySQL 数据库模型（存储关系型业务数据，如用户、会话、配置等）
    都应该继承此类。MySQL 用于存储应用的核心业务数据。
    """
    pass  # 无需额外功能，直接继承 DeclarativeBase 即可
