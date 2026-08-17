"""Chat API backed exclusively by the controlled agent workflow.

All knowledge-base evidence enters through ``local_knowledge_base``, whose
implementation is the hybrid retriever.  The removed legacy path used a
vector-only service, per-KB answer agents and direct attachment prompting.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, rate_limit
from app.db.session import MySQLSessionLocal, get_mysql_db
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.schemas.chat import (
    AskRequest,
    AskResponse,
    MessageResponse,
    SessionDetailResponse,
    SessionResponse,
)
from app.services.access_control_service import (
    KnowledgeBaseAccessDenied,
    list_accessible_kb_ids,
    resolve_authorized_kb_ids,
)
from app.services.agent_run_service import agent_run_service
from app.services.assistant_profile_service import assistant_profile_service
from app.services.answer_preference_service import answer_preference_service
from app.services.memory_service import agent_memory_service, session_memory_service
from app.services.standard_answer_cache_service import CacheReservation, standard_answer_cache_service


logger = logging.getLogger(__name__)
router = APIRouter()

_GENERAL_DISCLAIMER = (
    "This information is for reference only and does not constitute medical advice. "
    "Please consult a qualified healthcare professional for medical decisions."
)


def _tenant(user: User) -> int:
    return int(getattr(user, "tenant_id", 1) or 1)


def _get_all_user_kbs(current_user: User, db: Session) -> list[int]:
    """Compatibility alias retained for callers of the central ACL helper."""
    return list_accessible_kb_ids(current_user, db)


def _load_history(session_id: int, db: Session, user_id: int | None = None) -> list[dict]:
    if user_id is not None:
        owned = db.query(ChatSession.id).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).first()
        if not owned:
            raise HTTPException(status_code=404, detail="Session not found")
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    return [{"role": message.role, "content": message.content} for message in messages]


def _save_kb_ids(session: ChatSession, kb_ids: list[int] | None, db: Session) -> None:
    if kb_ids is not None:
        session.kb_ids_json = json.dumps(kb_ids)
        db.commit()


def _parse_kb_ids(session: ChatSession) -> list[int] | None:
    if not session.kb_ids_json:
        return None
    try:
        value = json.loads(session.kb_ids_json)
        return [int(item) for item in value] if isinstance(value, list) else None
    except (json.JSONDecodeError, TypeError, ValueError):
        return None


def _authorize_kbs(current_user: User, db: Session, requested: list[int] | None) -> list[int]:
    try:
        return resolve_authorized_kb_ids(current_user, requested, db)
    except KnowledgeBaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail="Knowledge base access denied") from exc


def _resolve_request_kbs(
    current_user: User,
    db: Session,
    requested: list[int] | None,
    session: ChatSession,
) -> list[int]:
    resolved = _authorize_kbs(current_user, db, requested if requested is not None else _parse_kb_ids(session))
    _save_kb_ids(session, resolved, db)
    return resolved


def _get_or_create_session(
    db: Session,
    current_user: User,
    *,
    session_id: int | None,
    question: str,
    session_type: str = "qa",
) -> ChatSession:
    if session_id:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session
    session = ChatSession(
        user_id=current_user.id,
        title=question[:100],
        session_type=session_type,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _conversation_summary(history: list[dict]) -> str:
    # The last row is the current user message and must not be duplicated.
    previous = history[:-1] if history and history[-1].get("role") == "user" else history
    lines = [f"{item.get('role', 'user')}: {item.get('content', '')}" for item in previous[-10:]]
    return "\n".join(lines)[-4000:]


def _knowledge_revision(db: Session, kb_ids: list[int]) -> str:
    """Fingerprint cache entries with the currently indexed document versions."""
    if not kb_ids:
        return "empty"
    rows = db.query(
        Document.kb_id,
        func.max(Document.updated_at),
        func.count(Document.id),
        func.coalesce(func.sum(Document.chunk_count), 0),
    ).filter(
        Document.kb_id.in_(kb_ids),
        Document.version_status == "active",
    ).group_by(Document.kb_id).all()
    return json.dumps([
        [int(row[0]), row[1].isoformat() if row[1] else "", int(row[2]), int(row[3] or 0)]
        for row in sorted(rows, key=lambda item: int(item[0]))
    ], separators=(",", ":"))


def _cached_state(
    reservation: CacheReservation,
    *,
    session: ChatSession,
    current_user: User,
    question: str,
    kb_ids: list[int],
    preferred_style: str,
) -> dict:
    cached = reservation.cached or {}
    cached_at = float(cached.get("cached_at") or time.time())
    variants = list(cached.get("answer_variants") or [])
    variants.sort(key=lambda item: (item.get("style") != preferred_style, item.get("variant_id", "")))
    primary = variants[0] if variants else None
    return {
        "request_id": f"cache_{(reservation.key or '')[-16:]}",
        "thread_id": f"chat_{session.id}",
        "user_id": current_user.id,
        "tenant_id": _tenant(current_user),
        "raw_query": question,
        "authorized_kb_ids": kb_ids,
        "final_answer": primary.get("answer") if primary else (cached.get("final_answer") or ""),
        "citations": primary.get("citations", []) if primary else (cached.get("citations") or []),
        "safety_status": cached.get("safety_status") or "pass",
        "risk_level": cached.get("risk_level") or "low",
        "evidence_status": cached.get("evidence_status") or "sufficient",
        "status": "completed",
        "errors": [],
        "public_events": [{
            "type": "cache_hit",
            "cache": "redis_standard_answer",
            "lookup_latency_ms": round(reservation.lookup_latency_ms, 3),
            "age_seconds": round(max(0.0, time.time() - cached_at), 3),
        }],
        "cache_hit": True,
        "cache_age_seconds": max(0.0, time.time() - cached_at),
        "cache_lookup_latency_ms": reservation.lookup_latency_ms,
        "agent_call_count": 0,
        "tool_call_count": 0,
        "answer_style_preference": preferred_style,
        "answer_variants": variants,
        "recommended_variant_id": primary.get("variant_id") if primary else cached.get("recommended_variant_id"),
    }


def _display_answer(state: dict) -> str:
    answer = str(state.get("final_answer") or "").strip()
    if answer:
        return answer
    questions = [str(item).strip() for item in state.get("clarification_questions", []) if str(item).strip()]
    if questions:
        return "为了更准确地回答，请补充以下信息：\n" + "\n".join(f"- {item}" for item in questions)
    if state.get("status") == "waiting_for_review":
        return "该问题需要人工审核，审核完成后才能提供结论。"
    errors = state.get("errors") or []
    if errors:
        return "本次任务未能完成，请稍后重试。"
    return "当前证据不足，无法给出可靠回答。"


def _run_controlled(
    *,
    question: str,
    session: ChatSession,
    current_user: User,
    kb_ids: list[int],
    history: list[dict],
    assistant_profile: str,
    answer_style_preference: str,
) -> dict:
    """The single runtime entry point for every chat endpoint."""
    return agent_run_service.start(
        query=question,
        user_id=current_user.id,
        tenant_id=_tenant(current_user),
        authorized_kb_ids=kb_ids,
        thread_id=f"chat_{session.id}",
        conversation_summary=_conversation_summary(history),
        assistant_profile=assistant_profile,
        answer_style_preference=answer_style_preference,
    )


def _save_assistant(db: Session, session_id: int, state: dict, answer: str) -> ChatMessage:
    message = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=answer,
        references_json=state.get("citations", []),
        safety_flag=state.get("safety_status") or state.get("risk_level"),
        answer_variants_json=state.get("answer_variants") or None,
        recommended_variant_id=state.get("recommended_variant_id"),
        selected_variant_id=None,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


def _execute_request(
    req: AskRequest,
    db: Session,
    current_user: User,
    *,
    session_type: str = "qa",
    kb_ids_override: list[int] | None = None,
) -> tuple[ChatSession, dict, str]:
    requested = kb_ids_override if kb_ids_override is not None else req.kb_ids
    if not req.session_id:
        _authorize_kbs(current_user, db, requested)
    session = _get_or_create_session(
        db,
        current_user,
        session_id=req.session_id,
        question=req.question,
        session_type=session_type,
    )
    kb_ids = _resolve_request_kbs(current_user, db, requested, session)
    db.add(ChatMessage(session_id=session.id, role="user", content=req.question))
    db.commit()
    history = _load_history(session.id, db, current_user.id)
    preference = answer_preference_service.get_profile(
        db, tenant_id=_tenant(current_user), user_id=current_user.id,
    )
    reservation = standard_answer_cache_service.lookup(
        tenant_id=_tenant(current_user),
        question=req.question,
        assistant_profile=req.assistant_profile,
        existing_session_id=req.session_id,
        kb_ids=kb_ids,
        kb_revision=_knowledge_revision(db, kb_ids),
        session_type=session_type,
    )
    if reservation.cached:
        state = _cached_state(
            reservation, session=session, current_user=current_user,
            question=req.question, kb_ids=kb_ids,
            preferred_style=preference["preferred_style"],
        )
        return session, state, _display_answer(state)

    started = time.perf_counter()
    try:
        state = _run_controlled(
            question=req.question,
            session=session,
            current_user=current_user,
            kb_ids=kb_ids,
            history=history,
            assistant_profile=req.assistant_profile,
            answer_style_preference=preference["preferred_style"],
        )
    except Exception:
        standard_answer_cache_service.release(reservation)
        raise
    generation_latency_ms = (time.perf_counter() - started) * 1000
    standard_answer_cache_service.store(
        reservation,
        tenant_id=_tenant(current_user),
        state=state,
        generation_latency_ms=generation_latency_ms,
    )
    state["cache_hit"] = False
    return session, state, _display_answer(state)


def _persist_session_memory(
    db: Session,
    *,
    session: ChatSession,
    current_user: User,
    question: str,
    answer: str,
    state: dict,
    assistant_profile: str,
) -> None:
    profile = assistant_profile_service.get(assistant_profile)
    if not profile.session_memory_enabled:
        return
    unresolved = []
    for index, item in enumerate(state.get("unresolved_questions") or state.get("clarification_questions") or []):
        if isinstance(item, dict):
            unresolved.append(item)
        else:
            unresolved.append({
                "question_id": f"{state.get('request_id', 'chat')}:{index}",
                "description": str(item),
                "status": "waiting_for_user",
                "created_at": state.get("created_at") or datetime.now(timezone.utc),
                "expires_at": None,
            })
    session_memory_service.upsert(
        db,
        tenant_id=_tenant(current_user),
        user_id=current_user.id,
        thread_id=f"chat_{session.id}",
        messages=[
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        active_topic=state.get("active_topic") or question[:200],
        unresolved_questions=unresolved,
        confirmed_constraints=state.get("confirmed_constraints") or [],
    )
    agent_memory_service.learn_preferences_from_message(
        db,
        tenant_id=_tenant(current_user),
        user_id=current_user.id,
        text=question,
        source_message_id=str(state.get("request_id") or f"chat:{session.id}"),
    )
    db.commit()


def _response(
    session: ChatSession,
    question: str,
    state: dict,
    answer: str,
    disclaimer: str,
    assistant_profile: str,
    message_id: int | None = None,
) -> AskResponse:
    effective_disclaimer = (
        None
        if state.get("intent") == "general_knowledge" and assistant_profile == "general_qa"
        else disclaimer
    )
    return AskResponse(
        session_id=session.id,
        question=question,
        answer=answer,
        references=state.get("citations", []),
        safety_flag=state.get("safety_status") or state.get("risk_level"),
        disclaimer=effective_disclaimer,
        assistant_profile=assistant_profile,
        cache_hit=bool(state.get("cache_hit")),
        cache_age_seconds=state.get("cache_age_seconds"),
        cache_lookup_latency_ms=state.get("cache_lookup_latency_ms"),
        answer_variants=state.get("answer_variants") or [],
        recommended_variant_id=state.get("recommended_variant_id"),
        message_id=message_id,
    )


@router.get("/assistants")
def list_assistants(current_user: User = Depends(get_current_user)):
    del current_user
    return {
        "default": "memory_qa",
        "items": assistant_profile_service.list(),
    }


@router.get("/cache/metrics")
def standard_answer_cache_metrics(current_user: User = Depends(get_current_user)):
    return standard_answer_cache_service.metrics(_tenant(current_user))


@router.post("/ask", response_model=AskResponse)
def ask_question(
    req: AskRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(rate_limit("chat")),
):
    session, state, answer = _execute_request(req, db, current_user)
    message = _save_assistant(db, session.id, state, answer)
    _persist_session_memory(
        db, session=session, current_user=current_user, question=req.question,
        answer=answer, state=state, assistant_profile=req.assistant_profile,
    )
    return _response(session, req.question, state, answer, _GENERAL_DISCLAIMER, req.assistant_profile, message.id)


@router.post("/ask/stream")
def ask_question_stream(
    req: AskRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
    _: None = Depends(rate_limit("chat")),
):
    session, state, answer = _execute_request(req, db, current_user)

    async def event_generator():
        for event in state.get("public_events", []):
            yield f"event: {event.get('type', 'metadata')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        if answer:
            yield f"event: answer_delta\ndata: {json.dumps({'token': answer}, ensure_ascii=False)}\n\n"
        for citation in state.get("citations", []):
            yield f"event: citation\ndata: {json.dumps(citation, ensure_ascii=False)}\n\n"
        if state.get("answer_variants"):
            variant_event = {
                "type": "answer_variants",
                "items": state["answer_variants"],
                "recommended_variant_id": state.get("recommended_variant_id"),
            }
            yield f"event: answer_variants\ndata: {json.dumps(variant_event, ensure_ascii=False)}\n\n"

        message_id = None
        db2 = MySQLSessionLocal()
        try:
            message_id = _save_assistant(db2, session.id, state, answer).id
            _persist_session_memory(
                db2, session=session, current_user=current_user, question=req.question,
                answer=answer, state=state, assistant_profile=req.assistant_profile,
            )
        except Exception:
            db2.rollback()
            logger.exception("Failed to save controlled streamed answer")
        finally:
            db2.close()
        done = {
            "done": True,
            "session_id": session.id,
            "message_id": message_id,
            "agent_run_id": state.get("request_id"),
            "status": state.get("status"),
            "safety_flag": state.get("safety_status") or state.get("risk_level"),
            "thinking": "",
            "assistant_profile": req.assistant_profile,
            "cache_hit": bool(state.get("cache_hit")),
            "cache_age_seconds": state.get("cache_age_seconds"),
            "cache_lookup_latency_ms": state.get("cache_lookup_latency_ms"),
            "recommended_variant_id": state.get("recommended_variant_id"),
        }
        yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _typed_kb_scope(current_user: User, db: Session, requested: list[int] | None, kb_type: str) -> list[int]:
    if requested is not None:
        return _authorize_kbs(current_user, db, requested)
    accessible = list_accessible_kb_ids(current_user, db)
    if not accessible:
        return []
    rows = db.query(KnowledgeBase.id).filter(
        KnowledgeBase.id.in_(accessible),
        KnowledgeBase.type == kb_type,
    ).all()
    return [int(row[0]) for row in rows]


def _typed_question(
    req: AskRequest,
    db: Session,
    current_user: User,
    *,
    session_type: str,
    kb_type: str | None,
    disclaimer: str,
) -> AskResponse:
    scope = _typed_kb_scope(current_user, db, req.kb_ids, kb_type) if kb_type else _authorize_kbs(current_user, db, req.kb_ids)
    typed_req = req.model_copy(update={"session_id": None})
    session, state, answer = _execute_request(
        typed_req,
        db,
        current_user,
        session_type=session_type,
        kb_ids_override=scope,
    )
    message = _save_assistant(db, session.id, state, answer)
    _persist_session_memory(
        db, session=session, current_user=current_user, question=req.question,
        answer=answer, state=state, assistant_profile=req.assistant_profile,
    )
    return _response(session, req.question, state, answer, disclaimer, req.assistant_profile, message.id)


@router.post("/health", response_model=AskResponse)
def health_consult(
    req: AskRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    return _typed_question(
        req,
        db,
        current_user,
        session_type="health",
        kb_type=None,
        disclaimer=(
            "This information is for reference only and does not constitute medical advice. "
            "If you are experiencing a medical emergency, please call emergency services immediately."
        ),
    )


@router.post("/drug", response_model=AskResponse)
def drug_qa(
    req: AskRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    return _typed_question(
        req,
        db,
        current_user,
        session_type="drug",
        kb_type="drug",
        disclaimer=(
            "This information is based on the retrieved drug evidence. "
            "Do not adjust or stop medication without consulting a doctor or pharmacist."
        ),
    )


@router.post("/paper", response_model=AskResponse)
def paper_qa(
    req: AskRequest,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    return _typed_question(
        req,
        db,
        current_user,
        session_type="paper",
        kb_type="paper",
        disclaimer="This summary is for reference only and does not constitute medical advice.",
    )


@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
    type: Optional[str] = None,
):
    query = db.query(ChatSession).filter(ChatSession.user_id == current_user.id)
    if type:
        query = query.filter(ChatSession.session_type == type)
    sessions = query.order_by(ChatSession.updated_at.desc()).all()
    return [
        SessionResponse(
            id=session.id,
            user_id=session.user_id,
            title=session.title,
            session_type=session.session_type,
            summary=session.summary,
            created_at=session.created_at,
            updated_at=session.updated_at,
            kb_ids=_parse_kb_ids(session),
        )
        for session in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session(
    session_id: int,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at.asc()).all()
    return SessionDetailResponse(
        session=SessionResponse(
            id=session.id,
            user_id=session.user_id,
            title=session.title,
            session_type=session.session_type,
            summary=session.summary,
            created_at=session.created_at,
            updated_at=session.updated_at,
            kb_ids=_parse_kb_ids(session),
        ),
        messages=[
            MessageResponse(
                id=message.id,
                session_id=message.session_id,
                role=message.role,
                content=message.content,
                references_json=message.references_json,
                safety_flag=message.safety_flag,
                answer_variants_json=message.answer_variants_json,
                recommended_variant_id=message.recommended_variant_id,
                selected_variant_id=message.selected_variant_id,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    db: Session = Depends(get_mysql_db),
    current_user: User = Depends(get_current_user),
):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()
    return {"message": "Session deleted"}
