from sqlalchemy import BigInteger, Column, DateTime, Integer, JSON, String, Text, func

from app.db.base import MySQLBase


class TaskOutbox(MySQLBase):
    __tablename__ = "task_outbox"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    idempotency_key = Column(String(128), nullable=False, unique=True, index=True)
    payload = Column(JSON, nullable=False)
    status = Column(String(20), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    task_id = Column(String(100), nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    dispatched_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
