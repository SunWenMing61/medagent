from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func

from app.db.base import MySQLBase


class KnowledgeSource(MySQLBase):
    __tablename__ = "knowledge_source"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kb_id = Column(BigInteger, nullable=False, index=True)
    source_type = Column(String(30), nullable=False)
    name = Column(String(255), nullable=False)
    config = Column(Text, nullable=False)
    sync_status = Column(String(20), default="idle")
    last_sync_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
