from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func

from app.db.base import MySQLBase


class KnowledgeBase(MySQLBase):
    __tablename__ = "knowledge_base"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    type = Column(String(20), default="general")  # general, drug, paper
    owner_id = Column(BigInteger, nullable=False, index=True)
    visibility = Column(String(20), default="private")  # private, public
    status = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
