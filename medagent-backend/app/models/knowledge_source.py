# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Text（文本）、Integer（整数）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class KnowledgeSource(MySQLBase):
    # 知识源模型，对应数据库中的 knowledge_source 表，定义从外部获取知识的数据源配置
    __tablename__ = "knowledge_source"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 所属知识库 ID，不可为空，建有索引用于快速查询
    kb_id = Column(BigInteger, nullable=False, index=True)
    # 数据源类型，不可为空，例如 pubmed（PubMed 文献）、msd_manual（默沙东诊疗手册）等
    source_type = Column(String(30), nullable=False)
    # 数据源显示名称，不可为空，最大长度 255
    name = Column(String(255), nullable=False)
    # 数据源配置，以 JSON 字符串形式存储的适配器专属配置，不可为空
    config = Column(Text, nullable=False)
    # 同步状态，默认值为 "idle"，可选值：idle（空闲）、syncing（同步中）、success（成功）、failed（失败）
    sync_status = Column(String(20), default="idle")
    # 最后成功同步时间，可为空
    last_sync_at = Column(DateTime, nullable=True)
    # 错误信息，同步失败时记录详细原因
    error_message = Column(Text, nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
    # 更新时间，默认使用 now()，并在更新时自动刷新
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
