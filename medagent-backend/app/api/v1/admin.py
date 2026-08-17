# 导入类型提示：列表和可选类型
from typing import List, Optional

# 从 FastAPI 导入路由、依赖注入、HTTP 异常
from fastapi import APIRouter, Depends, HTTPException
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session
# 从 SQLAlchemy 导入聚合函数（用于统计数据）
from sqlalchemy import func

# 导入管理员权限验证依赖
from app.core.dependencies import require_admin
# 导入 MySQL 数据库会话获取函数
from app.db.session import get_mysql_db
# 导入用户模型
from app.models.user import User
# 导入知识库模型
from app.models.knowledge_base import KnowledgeBase
# 导入文档模型
from app.models.document import Document
# 导入反馈模型
from app.models.feedback import Feedback
# 导入系统日志模型
from app.models.system_log import SystemLog
# 导入模型配置模型
from app.models.model_config import ModelConfig
# 导入聊天会话和消息模型
from app.models.chat import ChatSession, ChatMessage
# 导入用户相关的 Pydantic 模型
from app.schemas.user import UserResponse, AdminUserStatusRequest
# 导入知识库响应模型
from app.schemas.knowledge_base import KBResponse
# 导入反馈响应模型
from app.schemas.feedback import FeedbackResponse
# 导入通用消息响应模型
from app.schemas.common import MessageResponse

# 创建管理员路由实例
router = APIRouter()


# 获取所有用户列表接口：GET /api/admin/users
@router.get("/users", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_mysql_db),      # 数据库会话
    admin: User = Depends(require_admin),      # 需要管理员权限
):
    # 查询所有用户，按创建时间降序排列
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


# 更新用户状态接口：PUT /api/admin/users/{user_id}/status
@router.put("/users/{user_id}/status", response_model=MessageResponse)
def update_user_status(
    user_id: int,                                      # 用户 ID（路径参数）
    req: AdminUserStatusRequest,                       # 请求体（包含新状态）
    db: Session = Depends(get_mysql_db),               # 数据库会话
    admin: User = Depends(require_admin),               # 需要管理员权限
):
    # 查询目标用户
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # 禁止禁用其他管理员账号
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Cannot disable admin users")
    # 更新用户状态（1=启用，0=禁用）
    user.status = req.status
    db.commit()
    return {"message": "User status updated"}


# 获取所有知识库接口：GET /api/admin/kb
@router.get("/kb", response_model=List[KBResponse])
def list_all_kb(
    db: Session = Depends(get_mysql_db),      # 数据库会话
    admin: User = Depends(require_admin),      # 需要管理员权限
):
    # 查询所有知识库，按创建时间降序排列
    kbs = db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).all()
    return [
        KBResponse(
            id=kb.id, name=kb.name, description=kb.description,
            type=kb.type, owner_id=kb.owner_id, visibility=kb.visibility,
            status=kb.status, created_at=kb.created_at, updated_at=kb.updated_at,
        )
        for kb in kbs
    ]


# 获取所有反馈列表接口：GET /api/admin/feedback
@router.get("/feedback", response_model=List[FeedbackResponse])
def list_all_feedback(
    db: Session = Depends(get_mysql_db),      # 数据库会话
    admin: User = Depends(require_admin),      # 需要管理员权限
):
    # 查询所有反馈，按创建时间降序排列
    feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    return [
        FeedbackResponse(
            id=fb.id, user_id=fb.user_id, message_id=fb.message_id,
            feedback_type=fb.feedback_type, comment=fb.comment,
            created_at=fb.created_at,
        )
        for fb in feedbacks
    ]


# 获取系统日志接口：GET /api/admin/logs
@router.get("/logs", response_model=List[dict])
def list_logs(
    action: Optional[str] = None,       # 可选的操作类型筛选
    limit: int = 100,                    # 返回的最大日志条数，默认 100
    db: Session = Depends(get_mysql_db), # 数据库会话
    admin: User = Depends(require_admin), # 需要管理员权限
):
    # 查询所有系统日志，按创建时间降序排列
    query = db.query(SystemLog).order_by(SystemLog.created_at.desc())
    if action:
        # 如果指定了操作类型，按类型过滤
        query = query.filter(SystemLog.action == action)
    # 限制返回条数
    logs = query.limit(limit).all()
    # 将 ORM 对象转换为字典列表
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "detail": log.detail,
            "status": log.status,
            "latency_ms": log.latency_ms,
            "created_at": str(log.created_at) if log.created_at else None,
        }
        for log in logs
    ]


# 获取系统统计数据接口：GET /api/admin/stats
@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_mysql_db),      # 数据库会话
    admin: User = Depends(require_admin),      # 需要管理员权限
):
    # 统计用户总数
    total_users = db.query(func.count(User.id)).scalar() or 0

    # 统计知识库数量：管理员可以看到自己拥有的 + 公开的知识库（含全局聊天历史知识库）
    kb_filter = (
        (KnowledgeBase.owner_id == admin.id) |
        (KnowledgeBase.visibility == "public")
    )
    total_kbs = (
        db.query(func.count(KnowledgeBase.id))
        .filter(kb_filter)
        .scalar()
        or 0
    )

    # 构建可见知识库 ID 的子查询，用于文档统计
    visible_kb_ids = (
        db.query(KnowledgeBase.id)
        .filter(kb_filter)
        .subquery()
    )

    # 统计文档总数：仅统计属于可见知识库的文档
    total_documents = (
        db.query(func.count(Document.id))
        .filter(Document.kb_id.in_(visible_kb_ids))
        .scalar()
        or 0
    )
    # 手动上传文档数 = 总文档数（已移除在线知识源，所有文档均为本地上传）
    uploaded_documents = total_documents

    # 统计会话总数和消息总数
    total_sessions = db.query(func.count(ChatSession.id)).scalar() or 0
    total_messages = db.query(func.count(ChatMessage.id)).scalar() or 0

    # 统计今日活跃用户数（今日有创建会话的用户）
    from datetime import datetime
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    active_users_today = (
        db.query(func.count(func.distinct(ChatSession.user_id)))
        .filter(ChatSession.created_at >= today_start)
        .scalar()
        or 0
    )

    # 统计反馈总数
    feedback_count = db.query(func.count(Feedback.id)).scalar() or 0

    return {
        # 新命名（前端使用）
        "total_users": total_users,
        "total_kbs": total_kbs,
        "total_documents": total_documents,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "active_users_today": active_users_today,
        "uploaded_documents": uploaded_documents,
        # 旧命名（向后兼容）
        "user_count": total_users,
        "kb_count": total_kbs,
        "doc_count": total_documents,
        "feedback_count": feedback_count,
    }


# 获取模型配置接口：GET /api/admin/config/model
@router.get("/config/model", response_model=dict)
def get_model_config(
    db: Session = Depends(get_mysql_db),      # 数据库会话
    admin: User = Depends(require_admin),      # 需要管理员权限
):
    # 查询第一条模型配置记录
    config = db.query(ModelConfig).first()
    if not config:
        # 如果数据库中没有配置记录，返回默认值
        return {
            "llm_model": "gpt-4o-mini",                # 默认 LLM 模型名称
            "embedding_model": "text-embedding-3-small", # 默认嵌入模型名称
            "top_k": 5,                                 # 默认检索数量
            "similarity_threshold": 0.5,                # 默认相似度阈值
            "temperature": 0.7,                         # 默认生成温度
            "max_tokens": 2048,                         # 默认最大 token 数
        }
    # 返回数据库中的配置
    return {
        "id": config.id,
        "llm_model": config.llm_model,
        "embedding_model": config.embedding_model,
        "top_k": config.top_k,
        "similarity_threshold": config.similarity_threshold,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "updated_at": str(config.updated_at) if config.updated_at else None,
    }


# 更新模型配置接口：PUT /api/admin/config/model
@router.put("/config/model", response_model=MessageResponse)
def update_model_config(
    req: dict,                                    # 请求体（包含要更新的配置字段）
    db: Session = Depends(get_mysql_db),          # 数据库会话
    admin: User = Depends(require_admin),          # 需要管理员权限
):
    # 查询第一条模型配置记录
    config = db.query(ModelConfig).first()
    if not config:
        # 如果没有配置记录，创建一条新的
        config = ModelConfig()
        db.add(config)

    # 逐个字段更新（只更新请求中提供的字段）
    if "llm_model" in req:
        config.llm_model = req["llm_model"]
    if "embedding_model" in req:
        config.embedding_model = req["embedding_model"]
    if "top_k" in req:
        config.top_k = req["top_k"]
    if "similarity_threshold" in req:
        config.similarity_threshold = req["similarity_threshold"]
    if "temperature" in req:
        config.temperature = req["temperature"]
    if "max_tokens" in req:
        config.max_tokens = req["max_tokens"]

    # 提交事务
    db.commit()
    return {"message": "Model config updated"}
