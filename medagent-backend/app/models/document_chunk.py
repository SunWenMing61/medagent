from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func
from pgvector.sqlalchemy import Vector

from app.db.base import Base


class DocumentChunk(Base):
    __table_args__ = {"extend_existing": True}
    __tablename__ = "document_chunk"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    document_id = Column(BigInteger, nullable=False, index=True)
    kb_id = Column(BigInteger, nullable=False, index=True)
    chunk_index = Column(Integer, default=0)
    content = Column(Text, nullable=False)
    page_num = Column(Integer, nullable=True)
    embedding = Column(Vector(1024), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
