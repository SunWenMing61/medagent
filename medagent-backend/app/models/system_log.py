from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func

from app.db.base import MySQLBase


class SystemLog(MySQLBase):
    __tablename__ = "system_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    status = Column(String(20), default="success")
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
