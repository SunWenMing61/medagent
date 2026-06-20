from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.dependencies import require_admin
from app.db.session import get_mysql_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.system_log import SystemLog
from app.models.model_config import ModelConfig
from app.models.chat import ChatSession, ChatMessage
from app.schemas.user import UserResponse, AdminUserStatusRequest
from app.schemas.knowledge_base import KBResponse
from app.schemas.feedback import FeedbackResponse
from app.schemas.common import MessageResponse

router = APIRouter()


@router.get("/users", response_model=List[UserResponse])
def list_users(
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return users


@router.put("/users/{user_id}/status", response_model=MessageResponse)
def update_user_status(
    user_id: int,
    req: AdminUserStatusRequest,
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Cannot disable admin users")
    user.status = req.status
    db.commit()
    return {"message": "User status updated"}


@router.get("/kb", response_model=List[KBResponse])
def list_all_kb(
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    kbs = db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).all()
    return [
        KBResponse(
            id=kb.id, name=kb.name, description=kb.description,
            type=kb.type, owner_id=kb.owner_id, visibility=kb.visibility,
            status=kb.status, created_at=kb.created_at, updated_at=kb.updated_at,
        )
        for kb in kbs
    ]


@router.get("/feedback", response_model=List[FeedbackResponse])
def list_all_feedback(
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    feedbacks = db.query(Feedback).order_by(Feedback.created_at.desc()).all()
    return [
        FeedbackResponse(
            id=fb.id, user_id=fb.user_id, message_id=fb.message_id,
            feedback_type=fb.feedback_type, comment=fb.comment,
            created_at=fb.created_at,
        )
        for fb in feedbacks
    ]


@router.get("/logs", response_model=List[dict])
def list_logs(
    action: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    query = db.query(SystemLog).order_by(SystemLog.created_at.desc())
    if action:
        query = query.filter(SystemLog.action == action)
    logs = query.limit(limit).all()
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


@router.get("/stats", response_model=dict)
def get_stats(
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    # ── Users ──────────────────────────────────────────
    total_users = db.query(func.count(User.id)).scalar() or 0

    # ── KBs: same filter as KB management list page ────
    # Admin sees: own KBs + public KBs (includes the global chat_history KB)
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

    # Build subquery of visible KB ids for document filtering
    visible_kb_ids = (
        db.query(KnowledgeBase.id)
        .filter(kb_filter)
        .subquery()
    )

    # ── Documents: only those belonging to visible KBs ─
    total_documents = (
        db.query(func.count(Document.id))
        .filter(Document.kb_id.in_(visible_kb_ids))
        .scalar()
        or 0
    )
    online_documents = (
        db.query(func.count(Document.id))
        .filter(
            Document.kb_id.in_(visible_kb_ids),
            Document.source_id.isnot(None),
            Document.source_id > 0,
        )
        .scalar()
        or 0
    )
    uploaded_documents = total_documents - online_documents

    # ── Sessions & messages ────────────────────────────
    total_sessions = db.query(func.count(ChatSession.id)).scalar() or 0
    total_messages = db.query(func.count(ChatMessage.id)).scalar() or 0

    # ── Active users today ─────────────────────────────
    from datetime import datetime
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    active_users_today = (
        db.query(func.count(func.distinct(ChatSession.user_id)))
        .filter(ChatSession.created_at >= today_start)
        .scalar()
        or 0
    )

    feedback_count = db.query(func.count(Feedback.id)).scalar() or 0

    return {
        # New naming (used by frontend)
        "total_users": total_users,
        "total_kbs": total_kbs,
        "total_documents": total_documents,
        "total_sessions": total_sessions,
        "total_messages": total_messages,
        "active_users_today": active_users_today,
        "online_documents": online_documents,
        "uploaded_documents": uploaded_documents,
        # Legacy naming (backward compat)
        "user_count": total_users,
        "kb_count": total_kbs,
        "doc_count": total_documents,
        "feedback_count": feedback_count,
    }


@router.get("/config/model", response_model=dict)
def get_model_config(
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    config = db.query(ModelConfig).first()
    if not config:
        return {
            "llm_model": "gpt-4o-mini",
            "embedding_model": "text-embedding-3-small",
            "top_k": 5,
            "similarity_threshold": 0.5,
            "temperature": 0.7,
            "max_tokens": 2048,
        }
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


@router.put("/config/model", response_model=MessageResponse)
def update_model_config(
    req: dict,
    db: Session = Depends(get_mysql_db),
    admin: User = Depends(require_admin),
):
    config = db.query(ModelConfig).first()
    if not config:
        config = ModelConfig()
        db.add(config)

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

    db.commit()
    return {"message": "Model config updated"}
