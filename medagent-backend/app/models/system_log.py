# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Text（文本）、Integer（整数）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Text, Integer, DateTime, func

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class SystemLog(MySQLBase):
    # 系统日志模型，对应数据库中的 system_log 表，记录用户操作和系统事件
    __tablename__ = "system_log"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 操作用户 ID，可为空（匿名操作或系统自动操作时为空）
    user_id = Column(BigInteger, nullable=True)
    # 操作名称，不可为空，例如 "user_login"、"doc_upload" 等
    action = Column(String(100), nullable=False)
    # 操作详情，以文本形式记录附加信息，可为空
    detail = Column(Text, nullable=True)
    # 操作状态，默认值为 "success"，可选值：success（成功）、failure（失败）
    status = Column(String(20), default="success")
    # 操作延迟（毫秒），记录接口响应耗时，可为空
    latency_ms = Column(Integer, nullable=True)
    # 创建时间（即操作时间），使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
