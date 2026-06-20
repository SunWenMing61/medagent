"""API endpoints for online knowledge source management."""

import json
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.adapters import list_adapter_types, get_config_schema, get_adapter
from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db
from app.models.user import User
from app.models.knowledge_base import KnowledgeBase
from app.models.knowledge_source import KnowledgeSource
from app.schemas.knowledge_source import (
    SourceCreateRequest,
    SourceUpdateRequest,
    SourceResponse,
    SourceStatusResponse,
    SourceSyncResponse,
    SourceSchemaResponse,
)
from app.services.source_service import source_service
from app.tasks.source_tasks import enqueue_sync

router = APIRouter()


def _source_to_response(
    source: KnowledgeSource,
    document_count: int = 0,
) -> SourceResponse:
    return SourceResponse(
        id=source.id,
        kb_id=source.kb_id,
        source_type=source.source_type,
        name=source.name,
        config=source.config,
        sync_status=source.sync_status,
        document_count=document_count,
        last_sync_at=source.last_sync_at,
        error_message=source.error_message,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _check_kb_permission(kb_id: int, user: User, mysql_db: Session) -> KnowledgeBase:
    """Check if user has permission to access the KB."""
    kb = mysql_db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="知识库不存在")
    if kb.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权限操作此知识库")
    return kb


def _check_source_permission(source_id: int, user: User, mysql_db: Session):
    """Check if user has permission to access the source."""
    source = mysql_db.query(KnowledgeSource).filter(
        KnowledgeSource.id == source_id
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="知识源不存在")

    kb = mysql_db.query(KnowledgeBase).filter(
        KnowledgeBase.id == source.kb_id
    ).first()
    if not kb:
        raise HTTPException(status_code=404, detail="关联知识库不存在")

    if kb.owner_id != user.id and user.role != "admin":
        raise HTTPException(status_code=403, detail="无权限操作此知识源")
    return source


@router.post("/cleanup")
def cleanup_sources(
    current_user: User = Depends(get_current_user),
):
    """Delete all orphaned sources whose linked knowledge bases no longer exist."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可执行此操作")
    deleted = source_service.cleanup_orphaned_sources()
    return {"message": f"已清理 {deleted} 个失效知识源", "deleted_count": deleted}


@router.get("/schemas", response_model=dict)
def list_source_schemas():
    """Get config schemas for all available source types."""
    result = {}
    for info in list_adapter_types():
        st = info["source_type"]
        adapter = get_adapter(st)
        result[st] = SourceSchemaResponse(
            source_type=st,
            display_name=info["display_name"],
            config_schema=adapter.get_config_schema(),
            defaults=adapter.get_default_config(),
        )
    return result


@router.post("", response_model=SourceResponse, status_code=201)
def create_source(
    req: SourceCreateRequest,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new online knowledge source."""
    # Verify KB exists and user has permission
    _check_kb_permission(req.kb_id, current_user, mysql_db)

    # Validate adapter config
    try:
        adapter = get_adapter(req.source_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if req.config:
        is_valid, error = adapter.validate_config(req.config)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"配置验证失败: {error}")

    source = KnowledgeSource(
        kb_id=req.kb_id,
        source_type=req.source_type,
        name=req.name,
        config=json.dumps(req.config, ensure_ascii=False),
        sync_status="idle",
    )
    mysql_db.add(source)
    mysql_db.commit()
    mysql_db.refresh(source)

    return _source_to_response(source)


@router.get("", response_model=List[SourceResponse])
def list_sources(
    kb_id: Optional[int] = Query(None),
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """List knowledge sources, optionally filtered by kb_id.

    Orphaned sources (whose linked KB was deleted) are cleaned up automatically.
    """
    # Auto-cleanup sources whose KB no longer exists
    source_service.cleanup_orphaned_sources()

    query = mysql_db.query(KnowledgeSource)

    if kb_id:
        query = query.filter(KnowledgeSource.kb_id == kb_id)

    # Non-admin users can only see sources on their own KBs
    if current_user.role != "admin":
        admin_kb_ids = mysql_db.query(KnowledgeBase.id).filter(
            KnowledgeBase.owner_id == current_user.id
        ).subquery()
        query = query.filter(KnowledgeSource.kb_id.in_(admin_kb_ids))

    sources = query.order_by(KnowledgeSource.created_at.desc()).all()

    result = []
    for s in sources:
        count = source_service.get_source_document_count(s.id)
        result.append(_source_to_response(s, count))
    return result


@router.get("/{source_id}", response_model=SourceResponse)
def get_source(
    source_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single knowledge source by ID."""
    source = _check_source_permission(source_id, current_user, mysql_db)
    count = source_service.get_source_document_count(source.id)
    return _source_to_response(source, count)


@router.put("/{source_id}", response_model=SourceResponse)
def update_source(
    source_id: int,
    req: SourceUpdateRequest,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Update a knowledge source configuration."""
    source = _check_source_permission(source_id, current_user, mysql_db)

    if req.name is not None:
        source.name = req.name
    if req.config is not None:
        source.config = json.dumps(req.config, ensure_ascii=False)
        source.sync_status = "idle"  # Reset sync status on config change
    if req.kb_id is not None and req.kb_id != source.kb_id:
        # Verify new KB exists and user has permission
        _check_kb_permission(req.kb_id, current_user, mysql_db)
        source.kb_id = req.kb_id
        source.sync_status = "idle"  # Reset on KB change too

    mysql_db.commit()
    mysql_db.refresh(source)
    count = source_service.get_source_document_count(source.id)
    return _source_to_response(source, count)


@router.delete("/{source_id}")
def delete_source(
    source_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a knowledge source and all synced documents."""
    source = _check_source_permission(source_id, current_user, mysql_db)
    deleted_docs = source_service.delete_source(source.id)
    return {
        "message": "知识源已删除",
        "deleted_documents": deleted_docs,
    }


@router.post("/{source_id}/sync", response_model=SourceSyncResponse)
def trigger_sync(
    source_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger an asynchronous sync for a knowledge source."""
    source = _check_source_permission(source_id, current_user, mysql_db)

    if source.sync_status == "syncing":
        raise HTTPException(status_code=409, detail="该知识源正在同步中，请等待完成")

    # Update status immediately
    source.sync_status = "syncing"
    source.error_message = None
    mysql_db.commit()

    # Enqueue RQ task
    enqueue_sync(source_id)

    return SourceSyncResponse(source_id=source.id)


@router.get("/{source_id}/status", response_model=SourceStatusResponse)
def get_source_status(
    source_id: int,
    mysql_db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    """Get the current sync status of a knowledge source."""
    source = _check_source_permission(source_id, current_user, mysql_db)
    return SourceStatusResponse(
        id=source.id,
        sync_status=source.sync_status,
        last_sync_at=source.last_sync_at,
        error_message=source.error_message,
    )
