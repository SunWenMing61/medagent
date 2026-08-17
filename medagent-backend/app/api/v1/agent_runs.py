"""Public lifecycle API for controlled multi-agent runs."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user, require_admin
from app.db.session import get_mysql_db
from app.models.user import User
from app.schemas.agent_run import (
    AgentRunCreate, AgentRunResponse, AgentTraceResponse, ClarificationSubmission,
    HumanReviewSubmission,
)
from app.services.access_control_service import KnowledgeBaseAccessDenied, resolve_authorized_kb_ids
from app.services.agent_run_service import (
    AgentRunNotFound, InvalidAgentRunTransition, agent_run_service,
)
from app.services.checkpoint_service import checkpoint_service
from app.services.answer_preference_service import answer_preference_service
from app.services.memory_service import agent_memory_service, session_memory_service
from app.core.config import settings


router = APIRouter()


def _tenant(user: User) -> int:
    return int(getattr(user, "tenant_id", 1) or 1)


def _response(state: dict) -> AgentRunResponse:
    return AgentRunResponse(
        request_id=state["request_id"],
        thread_id=state["thread_id"],
        status=state.get("status", "failed"),
        current_node=state.get("current_agent", "unknown"),
        intent=state.get("intent", "unknown"),
        risk_level=state.get("risk_level", "low"),
        evidence_status=state.get("evidence_status", "not_run"),
        safety_status=state.get("safety_status", "not_run"),
        human_review_required=bool(state.get("human_review_required")),
        clarification_questions=state.get("clarification_questions", []),
        answer=state.get("final_answer", ""),
        citations=state.get("citations", []),
        errors=state.get("errors", []),
        agent_call_count=int(state.get("agent_call_count", 0)),
        tool_call_count=int(state.get("tool_call_count", 0)),
        answer_variants=state.get("answer_variants", []),
        recommended_variant_id=state.get("recommended_variant_id"),
    )


@router.post("", response_model=AgentRunResponse)
def create_agent_run(
    request: AgentRunCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    try:
        authorized = resolve_authorized_kb_ids(current_user, request.kb_ids, db)
        server_summary = request.conversation_summary
        if settings.ENABLE_NEW_MEMORY_ARCHITECTURE and request.thread_id and request.assistant_profile == "memory_qa":
            session = session_memory_service.get(
                db, tenant_id=_tenant(current_user), user_id=current_user.id, thread_id=request.thread_id,
            )
            server_summary = session.rolling_summary if session else ""
        state = agent_run_service.start(
            query=request.query,
            user_id=current_user.id,
            tenant_id=_tenant(current_user),
            authorized_kb_ids=authorized,
            thread_id=request.thread_id,
            conversation_summary=server_summary,
            assistant_profile=request.assistant_profile,
            answer_style_preference=answer_preference_service.get_profile(
                db, tenant_id=_tenant(current_user), user_id=current_user.id,
            )["preferred_style"],
        )
        if settings.ENABLE_NEW_MEMORY_ARCHITECTURE and request.assistant_profile == "memory_qa":
            agent_memory_service.learn_preferences_from_message(
                db,
                tenant_id=_tenant(current_user),
                user_id=current_user.id,
                text=request.query,
                source_message_id=state["request_id"],
            )
            messages = [{"role": "user", "content": request.query, "id": state["request_id"]}]
            if state.get("final_answer"):
                messages.append({"role": "assistant", "content": state["final_answer"], "id": f"{state['request_id']}:answer"})
            session_memory_service.upsert(
                db, user_id=current_user.id, tenant_id=_tenant(current_user),
                thread_id=state["thread_id"], messages=messages,
                active_topic=state.get("active_topic") or request.query[:200],
                unresolved_questions=[{
                    "question_id": f"{state['request_id']}:clarification",
                    "description": question,
                    "status": "waiting_for_user",
                    "created_at": state["created_at"],
                    "expires_at": None,
                } for question in state.get("clarification_questions", [])],
                confirmed_constraints=state.get("confirmed_constraints", []),
            )
        db.commit()
        return _response(state)
    except KnowledgeBaseAccessDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"Agent run failed: {exc}") from exc


@router.get("/{request_id}", response_model=AgentRunResponse)
def get_agent_run(request_id: str, current_user: User = Depends(get_current_user)):
    try:
        return _response(agent_run_service.get(
            request_id, user_id=current_user.id, tenant_id=_tenant(current_user)
        ))
    except AgentRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Agent run not found") from exc


@router.post("/{request_id}/clarification", response_model=AgentRunResponse)
def submit_clarification(
    request_id: str,
    submission: ClarificationSubmission,
    current_user: User = Depends(get_current_user),
):
    try:
        state = agent_run_service.submit_clarification(
            request_id,
            submission.response,
            user_id=current_user.id,
            tenant_id=_tenant(current_user),
        )
        return _response(state)
    except AgentRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Agent run not found") from exc
    except InvalidAgentRunTransition as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{request_id}/review", response_model=AgentRunResponse)
def submit_review(
    request_id: str,
    submission: HumanReviewSubmission,
    reviewer: User = Depends(require_admin),
    db: Session = Depends(get_mysql_db),
):
    try:
        return _response(agent_run_service.review(
            db,
            request_id,
            reviewer_id=reviewer.id,
            decision=submission.decision,
            edited_answer=submission.edited_answer,
            comment=submission.comment,
        ))
    except AgentRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Agent run or review not found") from exc
    except InvalidAgentRunTransition as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{request_id}", response_model=AgentRunResponse)
def cancel_agent_run(request_id: str, current_user: User = Depends(get_current_user)):
    state = checkpoint_service.cancel(request_id, user_id=current_user.id, tenant_id=_tenant(current_user))
    if not state:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return _response(state)


@router.get("/{request_id}/trace", response_model=AgentTraceResponse)
def get_agent_trace(
    request_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_mysql_db),
):
    try:
        return agent_run_service.trace_summary(
            db, request_id, user_id=current_user.id, tenant_id=_tenant(current_user)
        )
    except AgentRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Agent run not found") from exc


@router.get("/{request_id}/events")
def stream_agent_events(request_id: str, current_user: User = Depends(get_current_user)):
    try:
        state = agent_run_service.get(request_id, user_id=current_user.id, tenant_id=_tenant(current_user))
    except AgentRunNotFound as exc:
        raise HTTPException(status_code=404, detail="Agent run not found") from exc

    def event_stream():
        for event in state.get("public_events", []):
            yield f"event: {event.get('type', 'metadata')}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        yield f"event: done\ndata: {json.dumps({'status': state.get('status')})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
