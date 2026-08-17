"""Persistence, review, tracing and execution-boundary regressions."""

from unittest.mock import patch

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.agents.input_triage_agent import input_triage_agent
from app.db.base import MySQLBase
from app.graphs.graph_state import new_agent_state
from app.models.agent_runtime import AgentCheckpoint, AgentRun, AgentStep, HumanReview
from app.services.agent_run_service import AgentRunService
from app.services.agent_runtime_service import AgentRuntimeService, ToolLimitExceeded
from app.services.checkpoint_service import CheckpointService
from app.services.trace_service import TraceService
from app.tools.schemas import LocalRetrievalInput, ToolContext


@compiles(BigInteger, "sqlite")
def _sqlite_big_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    MySQLBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    yield factory
    MySQLBase.metadata.drop_all(engine)
    engine.dispose()


def test_checkpoint_is_versioned_scoped_and_creates_human_review(session_factory, monkeypatch):
    monkeypatch.setattr("app.services.checkpoint_service.settings.CHECKPOINTER_BACKEND", "database")
    service = CheckpointService(session_factory)
    state = new_agent_state(
        raw_query="test", user_id=11, tenant_id=22, authorized_kb_ids=[7], thread_id="thread-1"
    )
    service.save(state, "input_safety")
    state["status"] = "waiting_for_review"
    state["review_reason"] = "conflicting evidence"
    service.save(state, "human_review")

    assert service.load(state["request_id"], user_id=11, tenant_id=22)["state_version"] == "ma-v1"
    assert service.load(state["request_id"], user_id=12, tenant_id=22) is None
    assert service.load(state["request_id"], user_id=11, tenant_id=23) is None

    db = session_factory()
    try:
        checkpoints = db.query(AgentCheckpoint).order_by(AgentCheckpoint.sequence).all()
        review = db.query(HumanReview).filter_by(request_id=state["request_id"]).one()
        assert [row.sequence for row in checkpoints] == [1, 2]
        assert review.status == "pending"
        assert review.reason == "conflicting evidence"
    finally:
        db.close()


def test_human_reviewer_can_reject_a_waiting_run(session_factory, monkeypatch):
    checkpoint = CheckpointService(session_factory)
    monkeypatch.setattr("app.services.checkpoint_service.settings.CHECKPOINTER_BACKEND", "database")
    state = new_agent_state(raw_query="test", user_id=1, tenant_id=1, authorized_kb_ids=[])
    state.update(status="waiting_for_review", review_reason="high risk", current_agent="human_review")
    checkpoint.save(state, "human_review")

    db = session_factory()
    try:
        with patch("app.services.agent_run_service.checkpoint_service", checkpoint):
            result = AgentRunService().review(
                db,
                state["request_id"],
                reviewer_id=99,
                decision="reject",
                edited_answer=None,
                comment="insufficient evidence",
            )
        assert result["status"] == "rejected"
        assert result["human_review_required"] is False
        run = db.query(AgentRun).filter_by(request_id=state["request_id"]).one()
        review = db.query(HumanReview).filter_by(request_id=state["request_id"]).one()
        assert run.status == "rejected"
        assert review.status == "rejected"
        assert review.reviewer_id == 99
    finally:
        db.close()


def test_rule_agent_trace_never_claims_an_llm_call(session_factory, monkeypatch):
    monkeypatch.setattr("app.services.trace_service.settings.ENABLE_AGENT_TRACING", True)
    state = new_agent_state(raw_query="blood pressure", user_id=1, tenant_id=1, authorized_kb_ids=[])
    runtime = AgentRuntimeService(persist=True, trace=True)
    with patch("app.services.agent_runtime_service.trace_service", TraceService(session_factory)):
        runtime.run_agent(state, "input_triage", input_triage_agent.run, state["raw_query"])

    db = session_factory()
    try:
        step = db.query(AgentStep).one()
        assert step.model == "deterministic-rule-v1"
        assert step.input_tokens == 0
        assert step.output_tokens == 0
        assert step.cost_usd == 0
    finally:
        db.close()


def test_tool_limit_fails_before_any_tool_execution(monkeypatch):
    monkeypatch.setattr("app.services.agent_runtime_service.settings.TOOL_MAX_CALLS", 0)
    state = new_agent_state(raw_query="test", user_id=1, tenant_id=1, authorized_kb_ids=[5])
    payload = LocalRetrievalInput(
        context=ToolContext(
            request_id=state["request_id"], user_id=1, tenant_id=1, authorized_kb_ids=[5]
        ),
        query="test",
    )
    with pytest.raises(ToolLimitExceeded):
        AgentRuntimeService(persist=False, trace=False).run_tool(state, "local_knowledge_base", payload)
    assert state["tool_call_count"] == 0
