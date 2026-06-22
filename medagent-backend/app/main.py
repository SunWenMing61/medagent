# 导入 os 模块，用于操作系统级别的操作（如创建目录）
import os
# 导入 asynccontextmanager，用于创建异步上下文管理器（管理应用生命周期）
from contextlib import asynccontextmanager

# 导入 FastAPI 应用类
from fastapi import FastAPI
# 导入 CORS 中间件，用于处理跨域资源共享
from fastapi.middleware.cors import CORSMiddleware
# 导入静态文件挂载支持
from fastapi.staticfiles import StaticFiles

# 导入应用配置实例
from app.core.config import settings
# 导入 API 路由注册器（v1 版本的所有接口）
from app.api.v1.router import router
# 导入 SQLAlchemy 声明式基类（PostgreSQL 和 MySQL）
from app.db.base import Base, MySQLBase
# 导入数据库引擎实例（PostgreSQL 和 MySQL）
from app.db.session import pg_engine, mysql_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理器，替代 FastAPI 旧的 startup/shutdown 事件。

    在应用启动时执行初始化操作，在应用关闭时执行清理操作。

    参数:
        app (FastAPI): FastAPI 应用实例
    """
    # ==================== 启动阶段（yield 之前） ====================
    # 开发环境下自动创建数据库表；生产环境应使用 Alembic 迁移工具
    try:
        # 为 PostgreSQL 创建所有表（主要用于存储向量化的文档块，支持 pgvector）
        Base.metadata.create_all(bind=pg_engine)
        # 为 MySQL 创建所有表（存储所有关系型业务数据）
        MySQLBase.metadata.create_all(bind=mysql_engine)
        # 尝试添加 kb_ids_json 列（兼容旧数据库结构的迁移操作）
        _add_kb_ids_column()
        # 初始化默认数据（如管理员账号、默认模型配置）
        _init_default_data()
    except Exception as e:
        # 如果初始化过程发生异常，仅打印警告，不阻止应用启动
        print(f"Database initialization warning: {e}")

    # 确保上传文件目录存在，如果不存在则自动创建
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # yield 将控制权交给应用，此时应用开始接收请求
    yield

    # ==================== 关闭阶段（yield 之后） ====================
    pass  # 目前关闭阶段无需额外清理操作


def _init_default_data():
    """
    初始化默认系统数据（仅在首次启动时生效）。

    初始化内容包括：
    1. 默认管理员账号（用户名：admin）
    2. 默认模型配置（LLM、Embedding 等参数）
    3. 全局聊天历史知识库

    所有操作都是幂等的：如果数据已存在则跳过。
    """
    # 延迟导入，避免模块启动时的循环依赖问题
    from sqlalchemy.orm import Session
    from app.db.session import MySQLSessionLocal
    from app.models.user import User
    from app.models.model_config import ModelConfig
    from app.core.security import hash_password
    from app.services.chat_history_service import get_or_create_chat_history_kb

    # 创建一个独立的 MySQL 数据库会话（不依赖请求上下文）
    db: Session = MySQLSessionLocal()
    try:
        # 检查数据库中是否已存在 admin 用户
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            # 如果不存在，则创建默认管理员用户
            admin = User(
                username="admin",                                                  # 用户名：admin
                password_hash=hash_password(os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")),  # 密码哈希
                email="admin@medagent.com",                                        # 管理员邮箱
                role="admin",                                                      # 角色：管理员
                status=1,                                                          # 状态：启用
            )
            db.add(admin)  # 将新用户添加到会话中

        # 检查数据库中是否已存在模型配置
        config = db.query(ModelConfig).first()
        if not config:
            # 如果不存在，则创建默认模型配置
            config = ModelConfig(
                llm_model=settings.LLM_MODEL,                  # 默认 LLM 模型
                embedding_model=settings.EMBEDDING_MODEL,       # 默认 Embedding 模型
                top_k=settings.TOP_K,                           # 默认检索返回数量
                similarity_threshold=settings.SIMILARITY_THRESHOLD,  # 默认相似度阈值
                temperature=0.7,                                # 默认生成温度参数
                max_tokens=2048,                                # 默认最大输出令牌数
            )
            db.add(config)  # 将新配置添加到会话中

        # 提交所有数据库变更
        db.commit()
    except Exception:
        # 如果发生异常，回滚所有未提交的变更（保证原子性）
        db.rollback()
    finally:
        # 无论是否发生异常，在 finally 块中确保关闭数据库会话（释放连接）
        db.close()

    # 确保全局聊天历史知识库存在（幂等操作）
    try:
        get_or_create_chat_history_kb()
    except Exception:
        # 如果创建失败，忽略异常（可能因数据库尚未完全就绪等原因）
        pass


def _add_kb_ids_column():
    """
    为 chat_session 表添加 kb_ids_json 列（幂等操作）。

    该方法用于兼容旧的数据库 schema，如果列已存在则跳过不报错。
    该列用于存储每个聊天会话关联的知识库 ID 列表（JSON 格式）。
    """
    from sqlalchemy import text                     # 导入 SQL 文本表达式
    from app.db.session import mysql_engine         # 导入 MySQL 引擎

    try:
        # 连接 MySQL 数据库并执行 ALTER TABLE 语句
        with mysql_engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE chat_session ADD COLUMN kb_ids_json TEXT NULL AFTER summary")
                # 在 chat_session 表的 summary 列之后添加 kb_ids_json 列（TEXT 类型，可为空）
            )
            conn.commit()  # 提交 DDL 变更
    except Exception:
        # 如果列已存在或表不存在等，忽略异常（幂等保证）
        pass


# ==================== 创建 FastAPI 应用实例 ====================
app = FastAPI(
    title=settings.APP_NAME,      # API 文档标题，从配置中读取
    version=settings.VERSION,     # API 版本号，从配置中读取
    lifespan=lifespan,            # 设置应用生命周期管理器
)

# ==================== 配置 CORS 中间件 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # 允许所有来源的跨域请求（生产环境应限制具体域名）
    allow_credentials=True, # 允许携带认证信息（如 Cookies、Authorization 头）
    allow_methods=["*"],    # 允许所有 HTTP 方法（GET、POST、PUT、DELETE 等）
    allow_headers=["*"],    # 允许所有请求头
)

# ==================== 注册 API 路由 ====================
app.include_router(router)  # 将 v1 版本的所有 API 路由挂载到应用中


@app.get("/health")
def health_check():
    """
    健康检查接口（GET /health）。

    用于负载均衡器或容器编排系统（如 Kubernetes）的健康探测。
    返回应用当前运行状态、服务名称和版本号。

    返回:
        dict: {"status": "ok", "service": 应用名称, "version": 版本号}
    """
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.VERSION}
