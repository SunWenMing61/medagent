# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Text（文本）、Integer（整数）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class KnowledgeBase(MySQLBase):
    # 知识库模型，对应数据库中的 knowledge_base 表，用于管理和组织知识文档集合
    __tablename__ = "knowledge_base"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, nullable=False, default=1, index=True)
    # 知识库名称，不可为空，最大长度 255
    name = Column(String(255), nullable=False)
    # 知识库描述，可为空的文本字段
    description = Column(Text, nullable=True)
    # 知识库类型，默认值为 "general"，可选值：general（通用）、drug（药品）、paper（论文）
    type = Column(String(20), default="general")  # general, drug, paper
    # 所有者用户 ID，不可为空，建有索引用于快速查询
    owner_id = Column(BigInteger, nullable=False, index=True)
    # 可见性，默认值为 "private"，可选值：private（私有）、public（公开）
    visibility = Column(String(20), default="private")  # private, public
    # 状态，默认值为 1，用于逻辑删除或禁用（1=正常，0=禁用）
    status = Column(Integer, default=1)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
    # 更新时间，默认使用 now()，并在更新时自动刷新
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
