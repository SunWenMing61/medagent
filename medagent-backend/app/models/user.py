# 从 SQLAlchemy 导入列类型和工具函数：Column（列）、BigInteger（大整数）、String（字符串）、
# Integer（整数）、DateTime（日期时间）、func（SQL 函数，如 now()）
from sqlalchemy import Column, BigInteger, String, Integer, DateTime, func

# 从应用的基础模块导入 MySQLBase，这是所有 MySQL 模型表的基类
from app.db.base import MySQLBase


class User(MySQLBase):
    # 用户模型，对应数据库中的 user 表，存储系统用户账号信息
    __tablename__ = "user"

    # 主键 ID，自增的大整数
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, nullable=False, default=1, index=True)
    # 用户名，唯一且不可为空，建有索引用于快速查询和登录
    username = Column(String(100), unique=True, nullable=False, index=True)
    # 密码哈希值（非明文密码），不可为空，最大长度 255
    password_hash = Column(String(255), nullable=False)
    # 电子邮箱，可为空
    email = Column(String(255), nullable=True)
    # 用户角色，默认值为 "user"，可选值：user（普通用户）、admin（管理员）
    role = Column(String(20), default="user")
    # 用户状态，默认值为 1，用于启用/禁用账号（1=正常，0=禁用）
    status = Column(Integer, default=1)
    # 创建时间，使用数据库的 now() 函数作为默认值
    created_at = Column(DateTime, server_default=func.now())
    # 更新时间，默认使用 now()，并在更新时自动刷新
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
