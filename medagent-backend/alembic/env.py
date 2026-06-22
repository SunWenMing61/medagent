# 从 logging 模块导入 fileConfig 函数，用于加载 Alembic 的日志配置文件
from logging.config import fileConfig

# 从 SQLAlchemy 导入 engine_from_config（从配置字典创建引擎）和 pool（连接池配置）
from sqlalchemy import engine_from_config, pool
# 导入 Alembic 的 context 模块，提供迁移环境上下文
from alembic import context

# 导入 ORM 基类（PostgreSQL 的 Base 和 MySQL 的 MySQLBase）
from app.db.base import Base, MySQLBase
# 导入所有模型类（使用通配符导入确保所有模型的元数据被注册到对应的 Base 上）
# noqa: F401,F403 告诉 linter 绕过"未使用导入"和"通配符导入"的警告
from app.models import *  # noqa: F401,F403
# 导入应用配置，获取数据库连接 URL
from app.core.config import settings

# 获取 Alembic 的配置对象（对应 alembic.ini 中的 [alembic] 段）
config = context.config
# 用应用配置中的 PostgreSQL 数据库 URL 覆盖 alembic.ini 中的 sqlalchemy.url 配置项
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# 如果配置文件存在（alembic.ini 中指定了 log_file 等配置），则加载日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ==================== 迁移目标元数据 ====================
# 将 PostgreSQL 模型的元数据设为 Alembic 的迁移目标
# Alembic 会比较 target_metadata 中的模型定义与数据库当前状态，自动生成迁移脚本
target_metadata = Base.metadata

# 注意：MySQL 模型注册在 MySQLBase.metadata 上
# 如果需要为 MySQL 运行独立的迁移，需要创建另一套 Alembic 环境，
# 指向 MySQLBase.metadata。
# 目前（开发阶段），所有表都通过 main.py 中的 create_all() 自动创建。


def run_migrations_offline():
    """
    在"离线模式"下运行数据库迁移。

    离线模式不连接真实数据库，而是将迁移 SQL 语句输出到终端或文件。
    适用于：
    - 数据库尚不可用（如 CI/CD 流程中）
    - 需要人工审核迁移 SQL
    - DBA 需要手动执行迁移

    逻辑：
    1. 从配置中获取数据库 URL
    2. 配置 Alembic 上下文（使用字面绑定，生成可直接执行的 SQL）
    3. 开始事务并运行迁移
    """
    url = config.get_main_option("sqlalchemy.url")        # 从配置中获取数据库连接 URL
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)  # 配置离线上下文
    with context.begin_transaction():                     # 开始事务（离线模式下为逻辑事务）
        context.run_migrations()                          # 执行迁移操作（输出 SQL 而非连接到数据库）


def run_migrations_online():
    """
    在"在线模式"下运行数据库迁移。

    在线模式会直接连接到目标数据库，自动执行迁移 SQL。
    适用于：
    - 本地开发环境
    - 自动化部署流程

    逻辑：
    1. 从 Alembic 配置中创建数据库引擎（使用 NullPool，避免长连接）
    2. 连接到数据库
    3. 配置 Alembic 上下文
    4. 开始事务并运行迁移
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),  # 从 alembic.ini 获取数据库连接配置
        prefix="sqlalchemy.",                                # 配置键的前缀（只处理以 "sqlalchemy." 开头的键）
        poolclass=pool.NullPool,                             # 使用 NullPool，迁移完成后不保留连接池
    )
    with connectable.connect() as connection:                # 连接到数据库
        context.configure(connection=connection, target_metadata=target_metadata)  # 配置在线上下文
        with context.begin_transaction():                    # 开始数据库事务
            context.run_migrations()                         # 执行迁移操作


# ==================== 根据模式选择迁移执行方式 ====================
if context.is_offline_mode():
    # 如果 Alembic 以离线模式运行（通过 -x 参数或环境变量），执行离线迁移
    run_migrations_offline()
else:
    # 否则执行在线迁移（直接连接数据库）
    run_migrations_online()
