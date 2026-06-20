from sqlalchemy import Column, BigInteger, String, Integer, DateTime, Text, func

from app.db.base import MySQLBase


class Document(MySQLBase):
    __tablename__ = "document"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    kb_id = Column(BigInteger, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)
    file_size = Column(BigInteger, default=0)
    file_path = Column(String(500), nullable=True)
    source_id = Column(BigInteger, nullable=True, index=True)
    source_url = Column(String(1024), nullable=True)
    parse_status = Column(String(20), default="pending")  # pending, processing, success, failed
    vector_status = Column(String(20), default="pending")  # pending, processing, success, failed
    uploader_id = Column(BigInteger, nullable=False)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
