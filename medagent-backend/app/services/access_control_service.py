"""Single source of truth for knowledge-base authorization."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase
from app.models.user import User


class KnowledgeBaseAccessDenied(PermissionError):
    pass


def list_accessible_kb_ids(user: User, db: Session) -> list[int]:
    tenant_id = int(getattr(user, "tenant_id", 1) or 1)
    query = db.query(KnowledgeBase.id).filter(
        KnowledgeBase.status == 1,
        KnowledgeBase.tenant_id == tenant_id,
    )
    if user.role != "admin":
        query = query.filter(
            or_(
                KnowledgeBase.owner_id == user.id,
                and_(KnowledgeBase.visibility == "public", KnowledgeBase.status == 1),
            )
        )
    return sorted(int(row[0] if isinstance(row, tuple) else row.id) for row in query.all())


def resolve_authorized_kb_ids(
    user: User,
    requested_kb_ids: Sequence[int] | None,
    db: Session,
) -> list[int]:
    """Resolve `None` to all accessible KBs and validate every explicit ID.

    An explicit empty list remains empty (intentional non-RAG mode). No downstream
    retriever may reinterpret it as a wildcard.
    """
    accessible = set(list_accessible_kb_ids(user, db))
    if requested_kb_ids is None:
        return sorted(accessible)
    requested = list(dict.fromkeys(int(value) for value in requested_kb_ids))
    denied = sorted(set(requested) - accessible)
    if denied:
        raise KnowledgeBaseAccessDenied("One or more requested knowledge bases are not accessible")
    return requested


def require_kb_write_access(user: User, kb_id: int, db: Session) -> None:
    tenant_id = int(getattr(user, "tenant_id", 1) or 1)
    query = db.query(KnowledgeBase.id).filter(
        KnowledgeBase.id == int(kb_id),
        KnowledgeBase.status == 1,
        KnowledgeBase.tenant_id == tenant_id,
    )
    if user.role != "admin":
        query = query.filter(KnowledgeBase.owner_id == user.id)
    if not query.first():
        raise KnowledgeBaseAccessDenied("Knowledge base write access denied")
