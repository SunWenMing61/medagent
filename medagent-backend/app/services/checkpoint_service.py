"""Database-backed, versioned checkpoints for restart and human-review recovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_

from app.core.config import settings
from app.db.session import MySQLSessionLocal, PgSessionLocal
from app.models.agent_runtime import AgentCheckpoint, AgentRun, HumanReview
from app.models.memory import WorkflowCheckpoint


class CheckpointService:
    def __init__(self, session_factory=None, pg_session_factory=None) -> None:
        self.session_factory = session_factory or MySQLSessionLocal
        self.pg_session_factory = pg_session_factory or PgSessionLocal

    def save(self, state: dict, node_name: str) -> None:
        backend = settings.CHECKPOINTER_BACKEND
        if backend not in {"database", "mysql", "postgres"}:
            return
        self._save_mysql(state, node_name)
        if backend == "postgres":
            self._save_postgres(state, node_name)

    def _save_mysql(self, state: dict, node_name: str) -> None:
        db = self.session_factory()
        try:
            request_id = state["request_id"]
            run = db.query(AgentRun).filter(AgentRun.request_id == request_id).first()
            payload = self._serializable(state)
            if not run:
                run = AgentRun(
                    request_id=request_id,
                    thread_id=state["thread_id"],
                    user_id=state["user_id"],
                    tenant_id=state["tenant_id"],
                    state_json=payload,
                )
                db.add(run)
            run.status = state.get("status", "running")
            run.current_node = node_name
            run.state_version = state.get("state_version", "ma-v1")
            run.state_json = payload
            run.final_answer = state.get("final_answer") or None
            run.citations_json = state.get("citations") or None
            run.error_json = state.get("errors") or None
            run.agent_call_count = int(state.get("agent_call_count", 0))
            run.tool_call_count = int(state.get("tool_call_count", 0))
            run.token_count = int(state.get("tokens_used", 0))
            sequence = int(
                db.query(func.coalesce(func.max(AgentCheckpoint.sequence), 0))
                .filter(AgentCheckpoint.request_id == request_id)
                .scalar()
            ) + 1
            db.add(AgentCheckpoint(
                request_id=request_id,
                sequence=sequence,
                node_name=node_name,
                status=run.status,
                state_version=run.state_version,
                state_json=payload,
                expires_at=(datetime.now(timezone.utc) + timedelta(seconds=settings.CHECKPOINT_TTL)).replace(tzinfo=None),
            ))
            if run.status == "waiting_for_review":
                review = db.query(HumanReview).filter(HumanReview.request_id == request_id).first()
                if not review:
                    db.add(HumanReview(
                        request_id=request_id,
                        status="pending",
                        reason=state.get("review_reason") or "Controlled workflow requested human review.",
                    ))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _save_postgres(self, state: dict, node_name: str) -> None:
        db = self.pg_session_factory()
        try:
            request_id = state["request_id"]
            sequence = int(
                db.query(func.coalesce(func.max(WorkflowCheckpoint.sequence), 0))
                .filter(WorkflowCheckpoint.request_id == request_id)
                .scalar()
            ) + 1
            db.add(WorkflowCheckpoint(
                request_id=request_id,
                thread_id=state["thread_id"],
                tenant_id=int(state["tenant_id"]),
                user_id=int(state["user_id"]),
                sequence=sequence,
                node_name=node_name,
                status=state.get("status", "running"),
                state_version=state.get("state_version", "ma-v1"),
                state_json=self._serializable(state),
                expires_at=(datetime.now(timezone.utc) + timedelta(seconds=settings.CHECKPOINT_TTL)).replace(tzinfo=None),
            ))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def load(self, request_id: str, *, user_id: int, tenant_id: int) -> dict | None:
        if settings.CHECKPOINTER_BACKEND == "postgres":
            db = self.pg_session_factory()
            try:
                row = db.query(WorkflowCheckpoint).filter(
                    WorkflowCheckpoint.request_id == request_id,
                    WorkflowCheckpoint.user_id == int(user_id),
                    WorkflowCheckpoint.tenant_id == int(tenant_id),
                    or_(WorkflowCheckpoint.expires_at.is_(None), WorkflowCheckpoint.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)),
                ).order_by(WorkflowCheckpoint.sequence.desc()).first()
                return dict(row.state_json) if row else None
            finally:
                db.close()
        db = self.session_factory()
        try:
            run = db.query(AgentRun).filter(
                AgentRun.request_id == request_id,
                AgentRun.user_id == int(user_id),
                AgentRun.tenant_id == int(tenant_id),
            ).first()
            return dict(run.state_json) if run else None
        finally:
            db.close()

    def load_thread(self, thread_id: str, *, user_id: int, tenant_id: int) -> dict | None:
        """Resume the latest scoped state for a thread after process restart."""
        if settings.CHECKPOINTER_BACKEND == "postgres":
            db = self.pg_session_factory()
            try:
                row = db.query(WorkflowCheckpoint).filter(
                    WorkflowCheckpoint.thread_id == thread_id,
                    WorkflowCheckpoint.user_id == int(user_id),
                    WorkflowCheckpoint.tenant_id == int(tenant_id),
                    or_(WorkflowCheckpoint.expires_at.is_(None), WorkflowCheckpoint.expires_at > datetime.now(timezone.utc).replace(tzinfo=None)),
                ).order_by(WorkflowCheckpoint.created_at.desc(), WorkflowCheckpoint.sequence.desc()).first()
                return dict(row.state_json) if row else None
            finally:
                db.close()
        db = self.session_factory()
        try:
            run = db.query(AgentRun).filter(
                AgentRun.thread_id == thread_id,
                AgentRun.user_id == int(user_id),
                AgentRun.tenant_id == int(tenant_id),
            ).order_by(AgentRun.updated_at.desc()).first()
            return dict(run.state_json) if run else None
        finally:
            db.close()

    def cancel(self, request_id: str, *, user_id: int, tenant_id: int) -> dict | None:
        state = self.load(request_id, user_id=user_id, tenant_id=tenant_id)
        if not state:
            return None
        if state.get("status") not in {"completed", "failed", "cancelled"}:
            state["status"] = "cancelled"
            state["current_agent"] = "supervisor"
            self.save(state, "cancelled")
        return state

    @staticmethod
    def _serializable(state: dict) -> dict:
        return {key: value for key, value in state.items() if not key.startswith("_")}


checkpoint_service = CheckpointService()
