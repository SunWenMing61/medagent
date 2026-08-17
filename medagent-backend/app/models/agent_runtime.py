"""Durable records for controlled agent execution, checkpoints, traces and review."""

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint, func

from app.db.base import MySQLBase


class AgentRun(MySQLBase):
    __tablename__ = "agent_run"

    request_id = Column(String(64), primary_key=True)
    thread_id = Column(String(64), nullable=False, index=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    tenant_id = Column(BigInteger, nullable=False, index=True)
    status = Column(String(32), nullable=False, default="running", index=True)
    current_node = Column(String(64), nullable=False, default="input_safety")
    state_version = Column(String(32), nullable=False, default="ma-v1")
    state_json = Column(JSON, nullable=False)
    final_answer = Column(Text, nullable=True)
    citations_json = Column(JSON, nullable=True)
    error_json = Column(JSON, nullable=True)
    agent_call_count = Column(Integer, nullable=False, default=0)
    tool_call_count = Column(Integer, nullable=False, default=0)
    token_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AgentStep(MySQLBase):
    __tablename__ = "agent_step"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    agent_name = Column(String(64), nullable=False, index=True)
    agent_version = Column(String(32), nullable=False)
    prompt_version = Column(String(64), nullable=True)
    model = Column(String(128), nullable=True)
    status = Column(String(32), nullable=False)
    next_node = Column(String(64), nullable=True)
    latency_ms = Column(Float, nullable=False, default=0)
    input_tokens = Column(Integer, nullable=False, default=0)
    output_tokens = Column(Integer, nullable=False, default=0)
    cost_usd = Column(Float, nullable=False, default=0)
    confidence = Column(Float, nullable=True)
    error_code = Column(String(64), nullable=True)
    trace_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class AgentToolCall(MySQLBase):
    __tablename__ = "agent_tool_call"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    tool_name = Column(String(64), nullable=False, index=True)
    arguments_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False)
    latency_ms = Column(Float, nullable=False, default=0)
    error_code = Column(String(64), nullable=True)
    result_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, server_default=func.now())


class AgentCheckpoint(MySQLBase):
    __tablename__ = "agent_checkpoint"
    __table_args__ = (
        UniqueConstraint("request_id", "sequence", name="uq_agent_checkpoint_request_sequence"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    node_name = Column(String(64), nullable=False)
    status = Column(String(32), nullable=False)
    state_version = Column(String(32), nullable=False)
    state_json = Column(JSON, nullable=False)
    expires_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now())


class HumanReview(MySQLBase):
    __tablename__ = "human_review"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    request_id = Column(String(64), nullable=False, unique=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    reason = Column(Text, nullable=False)
    reviewer_id = Column(BigInteger, nullable=True)
    decision = Column(String(32), nullable=True)
    edited_answer = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    reviewed_at = Column(DateTime, nullable=True)

