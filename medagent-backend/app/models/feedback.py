# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Text（文本）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Text, DateTime, func

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class Feedback(MySQLBase):
    # 用户反馈模型，对应数据库中的 feedback 表，存储用户对 AI 回答的评价
    __tablename__ = "feedback"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 用户 ID，不可为空，建有索引用于快速查询
    user_id = Column(BigInteger, nullable=False, index=True)
    # 被反馈的消息 ID，不可为空
    message_id = Column(BigInteger, nullable=False)
    # 反馈类型，不可为空，例如 like（点赞）、dislike（点踩）等
    feedback_type = Column(String(50), nullable=False)
    # 用户附加的评论文字，可为空
    comment = Column(Text, nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
