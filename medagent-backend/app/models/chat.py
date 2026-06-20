from sqlalchemy import Column, BigInteger, String, Text, DateTime, func, JSON

from app.db.base import MySQLBase


class ChatSession(MySQLBase):
    __tablename__ = "chat_session"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    title = Column(String(255), nullable=True)
    session_type = Column(String(20), default="qa")  # qa, health, drug, paper
    summary = Column(Text, nullable=True)
    kb_ids_json = Column(Text, nullable=True)  # JSON array of selected KB IDs
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatMessage(MySQLBase):
    __tablename__ = "chat_message"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    session_id = Column(BigInteger, nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    references_json = Column(JSON, nullable=True)
    safety_flag = Column(String(50), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
