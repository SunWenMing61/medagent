# 从 SQLAlchemy 导入列类型和工具函数：BigInteger（大整数）、String（字符串）、Text（文本）、
# DateTime（日期时间）、func（SQL 函数，如 now()）、JSON（JSON 字段）
from sqlalchemy import Column, BigInteger, String, Text, DateTime, func, JSON

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class ChatSession(MySQLBase):
    # 聊天会话模型，对应数据库中的 chat_session 表
    __tablename__ = "chat_session"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 用户 ID，不可为空，建有索引用于快速查询
    user_id = Column(BigInteger, nullable=False, index=True)
    # 会话标题，可为空
    title = Column(String(255), nullable=True)
    # 会话类型，默认值为 "qa"，可选值：qa（问答）、health（健康）、drug（药品）、paper（论文）
    session_type = Column(String(20), default="qa")
    # 会话摘要，可为空的文本字段
    summary = Column(Text, nullable=True)
    # 选中的知识库 ID 列表，以 JSON 数组格式存储为文本，可为空
    kb_ids_json = Column(Text, nullable=True)  # JSON array of selected KB IDs
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
    # 更新时间，默认使用 now()，并在更新时自动刷新
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ChatMessage(MySQLBase):
    # 聊天消息模型，对应数据库中的 chat_message 表
    __tablename__ = "chat_message"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    # 所属会话 ID，不可为空，建有索引用于快速查询
    session_id = Column(BigInteger, nullable=False, index=True)
    # 消息角色，不可为空，可选值：user（用户）、assistant（助手/AI）
    role = Column(String(20), nullable=False)  # user, assistant
    # 消息内容，不可为空的文本字段
    content = Column(Text, nullable=False)
    # 引用来源信息，以 JSON 格式存储，可为空
    references_json = Column(JSON, nullable=True)
    # 安全标记，用于标记是否触发了安全过滤规则，可为空
    safety_flag = Column(String(50), nullable=True)
    answer_variants_json = Column(JSON, nullable=True)
    recommended_variant_id = Column(String(64), nullable=True)
    selected_variant_id = Column(String(64), nullable=True)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
