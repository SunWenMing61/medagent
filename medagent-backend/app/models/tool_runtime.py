"""Durable tool catalog, execution, health and policy audit records."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, Integer, JSON, String, Text, func

from app.db.base import MySQLBase


class ToolCatalog(MySQLBase):
    __tablename__ = "tool_registry"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(96), nullable=False, index=True)
    version = Column(String(32), nullable=False)
    category = Column(String(32), nullable=False, index=True)
    description = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True, index=True)
    gray_percentage = Column(Integer, nullable=False, default=100)
    metadata_json = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ToolCallRecord(MySQLBase):
    __tablename__ = "tool_call"

    tool_call_id = Column(String(64), primary_key=True)
    request_id = Column(String(64), nullable=False, index=True)
    thread_id = Column(String(64), nullable=False, index=True)
    agent_name = Column(String(64), nullable=False, index=True)
    tool_name = Column(String(96), nullable=False, index=True)
    tool_version = Column(String(32), nullable=False)
    arguments_hash = Column(String(64), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    latency_ms = Column(Float, nullable=False, default=0)
    status = Column(String(32), nullable=False, index=True)
    cache_hit = Column(Boolean, nullable=False, default=False)
    retries = Column(Integer, nullable=False, default=0)
    error_code = Column(String(64))
    created_at = Column(DateTime, server_default=func.now())


class ToolHealthRecord(MySQLBase):
    __tablename__ = "tool_health"

    tool_name = Column(String(96), primary_key=True)
    status = Column(String(32), nullable=False, default="healthy", index=True)
    last_success_at = Column(DateTime)
    error_rate_5m = Column(Float, nullable=False, default=0)
    p95_latency_ms = Column(Float, nullable=False, default=0)
    circuit_state = Column(String(16), nullable=False, default="closed")
    consecutive_failures = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ToolErrorRecord(MySQLBase):
    __tablename__ = "tool_error"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tool_call_id = Column(String(64), nullable=False, index=True)
    tool_name = Column(String(96), nullable=False, index=True)
    code = Column(String(64), nullable=False, index=True)
    message = Column(Text, nullable=False)
    retryable = Column(Boolean, nullable=False, default=False)
    details_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class ToolPolicyAudit(MySQLBase):
    __tablename__ = "tool_policy_audit"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    agent_name = Column(String(64), nullable=False, index=True)
    tool_name = Column(String(96), nullable=False, index=True)
    enabled = Column(Boolean, nullable=False)
    requires_approval = Column(Boolean, nullable=False, default=False)
    reason = Column(Text, nullable=False)
    context_summary_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())
