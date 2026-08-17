"""User-controlled long-term Memory and scoped session-summary APIs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.db.session import get_mysql_db
from app.models.user import User
from app.schemas.memory import (
    MemoryAuditResponse, MemoryCandidate, MemorySearchResponse, MemoryUpdateRequest,
    MemoryWriteRequest, SemanticMemoryResponse, SessionMemory,
)
from app.services.memory_service import agent_memory_service, session_memory_service


router = APIRouter()
session_router = APIRouter()


def _tenant(user: User) -> int:
    return int(getattr(user, "tenant_id", 1) or 1)


@router.get("", response_model=list[SemanticMemoryResponse] | MemorySearchResponse)
def list_or_search_memory(
    query: str | None = Query(default=None, max_length=1000),
    include_inactive: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    if query:
        items, tokens = agent_memory_service.retrieve(
            db, tenant_id=_tenant(current_user), user_id=current_user.id,
            query=query, agent_name="user_control", request_id=f"user-memory-search-{current_user.id}",
        )
        db.commit()
        return MemorySearchResponse(items=items, selected_tokens=tokens)
    return agent_memory_service.list_memories(
        db, tenant_id=_tenant(current_user), user_id=current_user.id,
        include_inactive=include_inactive,
    )


@router.post("", response_model=SemanticMemoryResponse, status_code=201)
def create_memory(
    request: MemoryWriteRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    candidate = MemoryCandidate(
        **request.model_dump(), memory_type="semantic", confidence=1.0, importance=0.8,
        reason_to_remember="User explicitly requested long-term storage through the Memory API.",
        source_type="user_explicit", source_role="user", explicit_instruction=True, confirmed=True,
    )
    try:
        result, decision = agent_memory_service.write_candidate(
            db, tenant_id=_tenant(current_user), user_id=current_user.id,
            candidate=candidate, agent_name="user_control", operator_id=str(current_user.id),
        )
        if not result:
            db.rollback()
            raise HTTPException(status_code=422, detail=decision.reason)
        db.commit()
        return result
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/settings")
def update_memory_settings(
    medical_sensitive_memory_enabled: bool,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    agent_memory_service.set_medical_sensitive(
        db, tenant_id=_tenant(current_user), user_id=current_user.id,
        enabled=medical_sensitive_memory_enabled,
    )
    db.commit()
    return agent_memory_service.settings(db, tenant_id=_tenant(current_user), user_id=current_user.id)


@router.patch("/{memory_id}", response_model=SemanticMemoryResponse)
def update_memory(
    memory_id: str,
    request: MemoryUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    try:
        result = agent_memory_service.update_memory(
            db, memory_id=memory_id, tenant_id=_tenant(current_user), user_id=current_user.id,
            value=request.value, sensitivity=request.sensitivity, expires_at=request.expires_at,
            reason=request.reason,
        )
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{memory_id}", status_code=204)
def delete_memory(
    memory_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    try:
        agent_memory_service.delete_memory(
            db, memory_id=memory_id, tenant_id=_tenant(current_user), user_id=current_user.id,
        )
        db.commit()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc


@router.post("/clear")
def clear_memory(current_user: User = Depends(get_current_user), db: Session = Depends(get_mysql_db)):
    count = agent_memory_service.clear(db, tenant_id=_tenant(current_user), user_id=current_user.id)
    db.commit()
    return {"deleted_count": count}


@router.post("/disable")
def disable_memory(current_user: User = Depends(get_current_user), db: Session = Depends(get_mysql_db)):
    agent_memory_service.set_enabled(db, tenant_id=_tenant(current_user), user_id=current_user.id, enabled=False)
    db.commit()
    return {"long_term_memory_enabled": False}


@router.post("/enable")
def enable_memory(current_user: User = Depends(get_current_user), db: Session = Depends(get_mysql_db)):
    agent_memory_service.set_enabled(db, tenant_id=_tenant(current_user), user_id=current_user.id, enabled=True)
    db.commit()
    return {"long_term_memory_enabled": True}


@router.get("/settings")
def memory_settings(current_user: User = Depends(get_current_user), db: Session = Depends(get_mysql_db)):
    result = agent_memory_service.settings(db, tenant_id=_tenant(current_user), user_id=current_user.id)
    db.commit()
    return result


@router.get("/audit", response_model=list[MemoryAuditResponse])
def memory_audit(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    return agent_memory_service.audit(db, tenant_id=_tenant(current_user), user_id=current_user.id, limit=limit)


@session_router.get("/{thread_id}", response_model=SessionMemory)
def get_session_memory(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    result = session_memory_service.get(db, tenant_id=_tenant(current_user), user_id=current_user.id, thread_id=thread_id)
    if not result:
        raise HTTPException(status_code=404, detail="Session memory not found")
    return result


@session_router.post("/{thread_id}/summary/rebuild", response_model=SessionMemory)
def rebuild_session_summary(
    thread_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    try:
        result = session_memory_service.rebuild_summary(
            db, tenant_id=_tenant(current_user), user_id=current_user.id, thread_id=thread_id,
        )
        db.commit()
        return result
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Session memory not found") from exc
