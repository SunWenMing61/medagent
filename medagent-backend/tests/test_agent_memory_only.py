"""Regression tests for key-only Agent Memory without conversation vectors."""

from sqlalchemy import BigInteger, create_engine, inspect
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
import app.tools  # noqa: F401
from app.db.base import MySQLBase
from app.models.memory import AgentMemory, AgentSession
from app.services.memory_service import AgentMemoryService, SessionMemoryService
from app.tools.registry import tool_registry


@compiles(BigInteger, "sqlite")
def _sqlite_big_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


def _database():
    engine = create_engine("sqlite://")
    MySQLBase.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)()


def test_models_have_no_conversation_vector_or_raw_message_columns():
    assert "conversation_memory" not in MySQLBase.metadata.tables
    assert {
        "embedding_json", "embedding_model", "embedding_dimension", "embedding_version",
    }.isdisjoint(AgentMemory.__table__.columns.keys())
    assert "recent_messages_json" not in AgentSession.__table__.columns
    assert "conversation_memory" not in tool_registry._items


def test_session_memory_persists_structured_keys_but_not_raw_messages():
    engine, db = _database()
    try:
        result = SessionMemoryService().upsert(
            db,
            tenant_id=1,
            user_id=2,
            thread_id="thread-1",
            messages=[
                {"id": "u1", "role": "user", "content": "请说明高血压随访重点"},
                {"id": "a1", "role": "assistant", "content": "这是一段不应重复入记忆库的完整回答"},
            ],
            active_topic="高血压随访",
            confirmed_constraints=[{"name": "language", "value": "zh-CN"}],
        )
        db.commit()
        row = db.query(AgentSession).one()
        columns = {item["name"] for item in inspect(engine).get_columns("agent_session")}
        assert "recent_messages_json" not in columns
        assert result.active_topic == "高血压随访"
        assert "完整回答" not in row.rolling_summary
        assert "confirmed_constraints" in row.rolling_summary
    finally:
        db.close()
        MySQLBase.metadata.drop_all(engine)
        engine.dispose()


def test_only_explicit_durable_preferences_enter_agent_memory():
    engine, db = _database()
    try:
        service = AgentMemoryService()
        ignored = service.learn_preferences_from_message(
            db, tenant_id=1, user_id=2, text="请解释高血压", source_message_id="m1",
        )
        remembered = service.learn_preferences_from_message(
            db, tenant_id=1, user_id=2,
            text="以后请用中文并尽量简洁回答",
            source_message_id="m2",
        )
        db.commit()
        assert ignored is None
        assert remembered is not None
        assert remembered.category == "communication_style"
        assert remembered.predicate == "answer_language"
        assert db.query(AgentMemory).count() == 1
    finally:
        db.close()
        MySQLBase.metadata.drop_all(engine)
        engine.dispose()
