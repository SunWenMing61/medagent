"""
数据库初始化脚本，用于在 PostgreSQL 和 MySQL 中创建/删除所有表。

可作为独立脚本运行：
  python init_db.py         # 创建所有表
  python init_db.py --drop  # 先删除所有表再重新创建
"""
# 导入声明式基类（PostgreSQL 的 Base 和 MySQL 的 MySQLBase）
from app.db.base import Base, MySQLBase
# 导入数据库引擎实例
from app.db.session import pg_engine, mysql_engine
# 导入应用配置，仅在打印数据库 URL 时使用
from app.core.config import settings


def init_database():
    """
    初始化数据库：创建两个数据库中的所有表。

    操作流程：
    1. 在 PostgreSQL 中创建所有表（主要是 document_chunk 表，支持 pgvector 向量搜索）
    2. 在 MySQL 中创建所有表（所有关系型业务模型：用户、会话、配置等）
    """
    print(f"PostgreSQL: {settings.DATABASE_URL}")                              # 打印 PostgreSQL 连接信息
    print("Creating PostgreSQL tables (document_chunk with pgvector)...")       # 提示正在创建 PostgreSQL 表
    Base.metadata.create_all(bind=pg_engine)                                   # 根据 ORM 模型元数据创建 PostgreSQL 表
    print("PostgreSQL tables created successfully!")                           # 创建成功提示

    print(f"MySQL: {settings.MYSQL_DATABASE_URL}")                            # 打印 MySQL 连接信息
    print("Creating MySQL tables (relational models)...")                      # 提示正在创建 MySQL 表
    MySQLBase.metadata.create_all(bind=mysql_engine)                           # 根据 ORM 模型元数据创建 MySQL 表
    print("MySQL tables created successfully!")                                # 创建成功提示


def drop_database():
    """
    删除数据库中的所有表（请谨慎使用！）。

    操作流程：
    1. 删除 PostgreSQL 中的所有表
    2. 删除 MySQL 中的所有表
    注意：此操作会永久丢失所有数据。
    """
    print("Dropping PostgreSQL tables...")                                     # 提示正在删除 PostgreSQL 表
    Base.metadata.drop_all(bind=pg_engine)                                     # 删除 PostgreSQL 中所有 ORM 模型对应的表
    print("PostgreSQL tables dropped!")                                        # 删除成功提示

    print("Dropping MySQL tables...")                                          # 提示正在删除 MySQL 表
    MySQLBase.metadata.drop_all(bind=mysql_engine)                             # 删除 MySQL 中所有 ORM 模型对应的表
    print("MySQL tables dropped!")                                             # 删除成功提示


if __name__ == "__main__":
    """
    当脚本直接运行时（而非被导入），解析命令行参数并执行相应操作。

    用法:
        python init_db.py         # 仅创建所有表
        python init_db.py --drop  # 先删除所有表再重新创建
    """
    import sys                   # 导入 sys 模块，用于读取命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "--drop":  # 如果命令行参数包含 "--drop"
        drop_database()          # 先删除所有表
    init_database()              # 重建所有表（无论是否执行了删除操作）
