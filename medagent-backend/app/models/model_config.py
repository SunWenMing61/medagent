# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Integer（整数）、Float（浮点数）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Integer, Float, DateTime, func

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class ModelConfig(MySQLBase):
    # 模型配置模型，对应数据库中的 model_config 表，存储 AI 模型及其检索参数配置
    __tablename__ = "model_config"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 大语言模型名称，默认值为 "gpt-4o-mini"
    llm_model = Column(String(100), default="gpt-4o-mini")
    # 向量嵌入模型名称，默认值为 "text-embedding-3-small"
    embedding_model = Column(String(100), default="text-embedding-3-small")
    # 检索时返回的最相似文档数量（top-k），默认值为 5
    top_k = Column(Integer, default=5)
    # 语义相似度阈值，低于此值的文档将被过滤，默认值为 0.5
    similarity_threshold = Column(Float, default=0.5)
    # LLM 生成温度参数，控制输出随机性，默认值为 0.7
    temperature = Column(Float, default=0.7)
    # LLM 生成的最大 token 数，默认值为 2048
    max_tokens = Column(Integer, default=2048)
    # 更新时间，默认使用 now()，并在更新时自动刷新
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
