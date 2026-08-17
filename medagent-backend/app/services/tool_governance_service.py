"""Best-effort durable audit for governed tool calls."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from app.db.session import MySQLSessionLocal
from app.models.tool_runtime import ToolCallRecord, ToolErrorRecord, ToolHealthRecord, ToolPolicyAudit
from app.tools.health import tool_health_manager


logger = logging.getLogger(__name__)


class ToolGovernanceService:
    def record(self, *, state: dict, definition, digest: str, result, policy_decision) -> None:
        db = MySQLSessionLocal()
        tool_call_id = f"tc_{uuid.uuid4().hex}"
        try:
            db.add(ToolCallRecord(
                tool_call_id=tool_call_id,
                request_id=state["request_id"],
                thread_id=state.get("thread_id") or state["request_id"],
                agent_name=state.get("current_agent", "unknown"),
                tool_name=definition.name,
                tool_version=definition.version,
                arguments_hash=digest,
                user_id=state["user_id"],
                tenant_id=state["tenant_id"],
                latency_ms=result.usage.latency_ms,
                status=result.status,
                cache_hit=result.usage.cache_hit,
                retries=result.usage.retries,
                error_code=result.error.code if result.error else None,
            ))
            if result.error:
                db.add(ToolErrorRecord(
                    tool_call_id=tool_call_id,
                    tool_name=definition.name,
                    code=result.error.code,
                    message=result.error.message[:2000],
                    retryable=result.error.retryable,
                    details_json=result.error.details or None,
                ))
            if policy_decision:
                db.add(ToolPolicyAudit(
                    request_id=state["request_id"],
                    agent_name=state.get("current_agent", "unknown"),
                    tool_name=definition.name,
                    enabled=policy_decision.enabled,
                    requires_approval=policy_decision.requires_approval,
                    reason=policy_decision.reason,
                    context_summary_json={
                        "intent": state.get("intent"), "risk_level": state.get("risk_level"),
                        "tool_call_count": state.get("tool_call_count"),
                    },
                ))
            health = tool_health_manager.status(definition.name)
            health_row = db.query(ToolHealthRecord).filter_by(tool_name=definition.name).first()
            if not health_row:
                health_row = ToolHealthRecord(tool_name=definition.name)
                db.add(health_row)
            health_row.status = health.status
            health_row.last_success_at = (
                datetime.fromisoformat(health.last_success_at).replace(tzinfo=None)
                if health.last_success_at else None
            )
            health_row.error_rate_5m = health.error_rate_5m
            health_row.p95_latency_ms = health.p95_latency_ms
            health_row.circuit_state = health.circuit_state
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Failed to persist governed tool audit")
        finally:
            db.close()


tool_governance_service = ToolGovernanceService()
