from sqlalchemy import Column, BigInteger, String, Integer, Float, DateTime, func

from app.db.base import MySQLBase


class ModelConfig(MySQLBase):
    __tablename__ = "model_config"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    llm_model = Column(String(100), default="gpt-4o-mini")
    embedding_model = Column(String(100), default="text-embedding-3-small")
    top_k = Column(Integer, default=5)
    similarity_threshold = Column(Float, default=0.5)
    temperature = Column(Float, default=0.7)
    max_tokens = Column(Integer, default=2048)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
