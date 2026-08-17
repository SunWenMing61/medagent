"""
知识图谱数据模型（MySQL）。

用于持久化存储从医疗文档中提取的实体和关系，
支持 GraphRAG 的图结构查询与推理。
"""

# 从 SQLAlchemy 导入列类型和工具函数
from sqlalchemy import Column, BigInteger, String, Text, DateTime, func

# 从应用的基础模块导入 MySQLBase，所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class GraphEntity(MySQLBase):
    """图谱实体模型，对应数据库中的 graph_entity 表。

    存储从文档中提取的命名实体（如疾病、药物、症状等），
    每个实体有一个类型标签和唯一名称。
    """
    __tablename__ = "graph_entity"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 所属知识库 ID，不可为空，建有索引用于按知识库检索
    kb_id = Column(BigInteger, nullable=False, index=True)
    # 实体类型：disease（疾病）/ drug（药物）/ symptom（症状）/ treatment（治疗）/ exam（检查）
    entity_type = Column(String(50), nullable=False, index=True)
    # 实体名称，如 "2型糖尿病"、"阿卡波糖"
    name = Column(String(500), nullable=False)
    # 元数据（JSON 格式），用于存储额外属性，如别名、描述、来源等
    metadata_json = Column(Text, nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())


class GraphRelation(MySQLBase):
    """图谱关系模型，对应数据库中的 graph_relation 表。

    存储实体之间的语义关系（如"药物治疗疾病"、"疾病引发症状"），
    构成知识图谱的边。
    """
    __tablename__ = "graph_relation"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 源实体 ID，引用 graph_entity 表的实体，不可为空，建有索引
    source_entity_id = Column(BigInteger, nullable=False, index=True)
    # 目标实体 ID，引用 graph_entity 表的实体，不可为空，建有索引
    target_entity_id = Column(BigInteger, nullable=False, index=True)
    # 关系类型：treats（治疗）/ causes（引发）/ side_effect（副作用）/ indicates（提示）/ contraindicates（禁忌）
    relation_type = Column(String(50), nullable=False, index=True)
    # 元数据（JSON 格式），用于存储关系强度、来源证据等额外信息
    metadata_json = Column(Text, nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
