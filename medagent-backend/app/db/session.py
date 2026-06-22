"""
数据库会话管理模块。

包含 PostgreSQL 和 MySQL 两种数据库的引擎创建和会话管理。
另外包含一个针对 psycopg2 在 Windows 系统上的猴子补丁（monkey-patch），
用于解决中文 locale（如 zh_CN/CP936）导致的 UnicodeDecodeError 异常。
"""
# 导入 logging 模块，用于记录日志信息
import logging
# 导入 wraps 装饰器（wraps 在此处未使用，但被保留以保持扩展性）
from functools import wraps

# 创建当前模块的日志记录器实例
logger = logging.getLogger(__name__)

# ==================== Windows 平台 psycopg2 编码问题修复 ====================
# 在 psycopg2 的 C 扩展加载 libpq 之前，先设置 locale 环境变量
# 这可以确保 libpq 使用 UTF-8 编码而非 CP936（中文 Windows 默认编码）
# 从而避免在连接 PostgreSQL 时出现 UnicodeDecodeError
import os as _os                      # 导入 os 模块并重命名为 _os，避免与其他 os 引用冲突
if _os.name == "nt":                  # 检查是否为 Windows 系统（nt = Windows NT）
    _os.environ.setdefault("LANG", "en_US.UTF-8")           # 设置默认语言环境为 UTF-8
    _os.environ.setdefault("LC_CTYPE", "en_US.UTF-8")       # 设置字符分类为 UTF-8
    _os.environ.setdefault("PGCLIENTENCODING", "UTF8")      # 设置 PostgreSQL 客户端编码为 UTF8

# 从 SQLAlchemy 导入 create_engine（创建数据库引擎）模块
from sqlalchemy import create_engine
# 从 SQLAlchemy ORM 导入 sessionmaker（创建会话工厂）和 Session（会话类型）模块
from sqlalchemy.orm import sessionmaker, Session

# 导入应用配置实例，获取数据库连接 URL
from app.core.config import settings

# ==================== PostgreSQL 引擎与会话（支持 pgvector 向量搜索） ====================
# 创建 PostgreSQL 数据库引擎
pg_engine = create_engine(
    settings.DATABASE_URL,            # 从配置中获取 PostgreSQL 连接 URL
    pool_pre_ping=True,               # 连接池启用"预检查"机制，每次从池中取出连接前先确认是否有效
    connect_args={"client_encoding": "utf8"},  # 连接参数：强制客户端编码为 UTF-8
)
# 创建 PostgreSQL 会话工厂
PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)
# autocommit=False: 禁用自动提交，需显式调用 commit()
# autoflush=False:  禁用自动刷新，需显式调用 flush()
# bind=pg_engine:   将会话工厂绑定到 PostgreSQL 引擎


def get_pg_db():
    """
    PostgreSQL 数据库会话依赖注入函数。

    在 FastAPI 路由中作为 Depends 使用，为每个请求提供独立的 PostgreSQL 会话。
    请求结束后自动关闭会话，将连接归还连接池。

    使用方法: db: Session = Depends(get_pg_db)

    类型:
        Generator[Session, None, None]: 产生一个 SQLAlchemy Session 对象
    """
    db: Session = PgSessionLocal()  # 从会话工厂创建一个新的数据库会话
    try:
        yield db                    # 将会话提供给调用方（FastAPI 路由处理函数）
    finally:
        db.close()                  # 请求处理完毕后关闭会话（释放连接到连接池）


# ==================== MySQL 引擎与会话（关系型业务数据） ====================
# 创建 MySQL 数据库引擎
mysql_engine = create_engine(settings.MYSQL_DATABASE_URL, pool_pre_ping=True)
# 创建 MySQL 会话工厂
MySQLSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mysql_engine)


def get_mysql_db():
    """
    MySQL 数据库会话依赖注入函数。

    在 FastAPI 路由中作为 Depends 使用，为每个请求提供独立的 MySQL 会话。
    请求结束后自动关闭会话，将连接归还连接池。

    使用方法: db: Session = Depends(get_mysql_db)

    类型:
        Generator[Session, None, None]: 产生一个 SQLAlchemy Session 对象
    """
    db: Session = MySQLSessionLocal()  # 从会话工厂创建一个新的数据库会话
    try:
        yield db                       # 将会话提供给调用方（FastAPI 路由处理函数）
    finally:
        db.close()                     # 请求处理完毕后关闭会话（释放连接到连接池）
