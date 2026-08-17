"""Agent/tool tracing that records metadata only, never raw medical text."""

from __future__ import annotations

from app.core.config import settings
from app.db.session import MySQLSessionLocal
from app.models.agent_runtime import AgentStep, AgentToolCall


class TraceService:
    def __init__(self, session_factory=None) -> None:
        self.session_factory = session_factory or MySQLSessionLocal

    def agent(self, **fields) -> None:
        if not settings.ENABLE_AGENT_TRACING:
            return
        db = self.session_factory()
        try:
            db.add(AgentStep(**fields))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def tool(self, **fields) -> None:
        if not settings.ENABLE_AGENT_TRACING:
            return
        db = self.session_factory()
        try:
            db.add(AgentToolCall(**fields))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


trace_service = TraceService()
