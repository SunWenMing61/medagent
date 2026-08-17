"""Physically separate Agent Memory metadata, audits, traces and PG checkpoints."""

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, Integer, JSON, String, Text,
    UniqueConstraint, Index, func,
)

from app.db.base import Base, MySQLBase


class AgentSession(MySQLBase):
    __tablename__ = "agent_session"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "thread_id", name="uq_agent_session_namespace"),
        Index("ix_agent_session_owner_status", "tenant_id", "user_id", "status"),
    )

    id = Column(String(64), primary_key=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    thread_id = Column(String(128), nullable=False, index=True)
    rolling_summary = Column(Text, nullable=False, default="")
    active_topic = Column(String(500))
    active_entities_json = Column(JSON, nullable=False, default=list)
    unresolved_questions_json = Column(JSON, nullable=False, default=list)
    confirmed_constraints_json = Column(JSON, nullable=False, default=list)
    latest_corrections_json = Column(JSON, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentMemory(MySQLBase):
    __tablename__ = "agent_memory"
    __table_args__ = (
        Index("ix_agent_memory_owner", "tenant_id", "user_id", "memory_type", "status"),
        Index("ix_agent_memory_agent", "tenant_id", "agent_name", "memory_type", "status"),
        Index("ix_agent_memory_fact", "tenant_id", "user_id", "subject", "predicate", "status"),
    )

    id = Column(String(64), primary_key=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, index=True)
    agent_name = Column(String(128), index=True)
    namespace = Column(String(500), nullable=False, index=True)
    memory_type = Column(String(32), nullable=False, index=True)
    category = Column(String(64), nullable=False, index=True)
    subject = Column(String(255), nullable=False)
    predicate = Column(String(255), nullable=False)
    value_json = Column(JSON, nullable=False)
    searchable_text = Column(Text, nullable=False)
    source_type = Column(String(32), nullable=False)
    source_message_ids_json = Column(JSON, nullable=False, default=list)
    confidence = Column(Float, nullable=False, default=1.0)
    importance = Column(Float, nullable=False, default=0.5)
    sensitivity = Column(String(32), nullable=False, default="normal", index=True)
    trust_level = Column(String(16), nullable=False, default="high")
    status = Column(String(32), nullable=False, default="active", index=True)
    valid_from = Column(DateTime)
    valid_to = Column(DateTime)
    expires_at = Column(DateTime, index=True)
    version = Column(Integer, nullable=False, default=1)
    can_support_medical_claim = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentEpisode(MySQLBase):
    __tablename__ = "agent_episode"
    __table_args__ = (
        Index("ix_agent_episode_scope", "tenant_id", "user_id", "event_type", "reusable"),
    )

    id = Column(String(64), primary_key=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, index=True)
    thread_id = Column(String(128), index=True)
    request_id = Column(String(128), index=True)
    event_type = Column(String(64), nullable=False, index=True)
    task_type = Column(String(64), nullable=False, index=True)
    situation_summary = Column(Text, nullable=False)
    action_summary = Column(Text, nullable=False)
    outcome_summary = Column(Text, nullable=False)
    success = Column(Boolean, nullable=False)
    quality_score = Column(Float)
    related_entities_json = Column(JSON, nullable=False, default=list)
    source_run_ids_json = Column(JSON, nullable=False, default=list)
    reusable = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, index=True)
    created_at = Column(DateTime, server_default=func.now())


class AgentProcedure(MySQLBase):
    __tablename__ = "agent_procedure"
    __table_args__ = (
        Index("ix_agent_procedure_route", "tenant_id", "agent_name", "task_type", "status"),
    )

    id = Column(String(64), primary_key=True)
    tenant_id = Column(BigInteger, index=True)
    scope = Column(String(32), nullable=False)
    agent_name = Column(String(128), index=True)
    task_type = Column(String(64), nullable=False, index=True)
    trigger_conditions_json = Column(JSON, nullable=False, default=dict)
    recommended_steps_json = Column(JSON, nullable=False, default=list)
    prohibited_actions_json = Column(JSON, nullable=False, default=list)
    required_tools_json = Column(JSON, nullable=False, default=list)
    fallback_strategy_json = Column(JSON, nullable=False, default=list)
    source = Column(String(32), nullable=False)
    evaluation_score = Column(Float)
    version = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="draft", index=True)
    approved_by = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentMemoryAudit(MySQLBase):
    __tablename__ = "agent_memory_audit"

    id = Column(String(64), primary_key=True)
    memory_id = Column(String(64), index=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, index=True)
    operation = Column(String(32), nullable=False, index=True)
    operator_type = Column(String(32), nullable=False)
    operator_id = Column(String(128))
    before_value_json = Column(JSON)
    after_value_json = Column(JSON)
    reason = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class UserMemorySetting(MySQLBase):
    __tablename__ = "user_memory_setting"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_user_memory_setting_owner"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    long_term_enabled = Column(Boolean, nullable=False, default=True)
    medical_sensitive_enabled = Column(Boolean, nullable=False, default=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class MemoryRetrievalTrace(MySQLBase):
    __tablename__ = "memory_retrieval_trace"

    id = Column(String(64), primary_key=True)
    request_id = Column(String(128), nullable=False, index=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    agent_name = Column(String(128), nullable=False, index=True)
    memory_types_json = Column(JSON, nullable=False)
    query_hash = Column(String(64), nullable=False)
    candidate_count = Column(Integer, nullable=False)
    selected_count = Column(Integer, nullable=False)
    memory_tokens = Column(Integer, nullable=False)
    latency_ms = Column(Float, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class RetrievalTrace(MySQLBase):
    __tablename__ = "retrieval_trace"

    request_id = Column(String(128), primary_key=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    original_query_hash = Column(String(64), nullable=False)
    standalone_query = Column(Text, nullable=False)
    routes_json = Column(JSON, nullable=False)
    entities_json = Column(JSON, nullable=False)
    constraints_json = Column(JSON, nullable=False)
    rankings_json = Column(JSON, nullable=False)
    filtered_json = Column(JSON, nullable=False)
    final_evidence_json = Column(JSON, nullable=False)
    timings_json = Column(JSON, nullable=False)
    status = Column(String(32), nullable=False, index=True)
    error_json = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())


class WorkflowCheckpoint(Base):
    """PostgreSQL-native restart checkpoint selected by CHECKPOINTER_BACKEND=postgres."""

    __tablename__ = "agent_workflow_checkpoint"
    __table_args__ = (
        UniqueConstraint("request_id", "sequence", name="uq_workflow_checkpoint_sequence"),
        Index("ix_workflow_checkpoint_thread", "tenant_id", "user_id", "thread_id", "sequence"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    thread_id = Column(String(128), nullable=False, index=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    node_name = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    state_version = Column(String(32), nullable=False)
    state_json = Column(JSON, nullable=False)
    expires_at = Column(DateTime, index=True)
    created_at = Column(DateTime, server_default=func.now())
