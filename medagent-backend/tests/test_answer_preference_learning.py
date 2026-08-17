from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401
from app.db.base import MySQLBase
from app.models.chat import ChatMessage, ChatSession
from app.models.memory import AgentMemory
from app.services.answer_preference_service import AnswerPreferenceService


@compiles(BigInteger, "sqlite")
def _sqlite_big_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


def _variants():
    return [
        {
            "variant_id": "variant_concise", "style": "concise_evidence",
            "label": "精炼证据版", "answer": "精炼回答", "citations": [],
            "safety_status": "pass", "request_id": "req_1",
        },
        {
            "variant_id": "variant_detailed", "style": "detailed_guidance",
            "label": "详细指导版", "answer": "详细回答", "citations": [],
            "safety_status": "pass", "request_id": "req_1",
        },
    ]


def test_pairwise_choice_is_idempotent_and_can_be_changed():
    engine = create_engine("sqlite://")
    MySQLBase.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(ChatSession(id=1, user_id=7, title="test", session_type="qa"))
        db.add(ChatMessage(
            id=10, session_id=1, role="assistant", content="精炼回答",
            answer_variants_json=_variants(), recommended_variant_id="variant_concise",
        ))
        db.commit()
        service = AnswerPreferenceService()

        first = service.record_choice(
            db, tenant_id=3, user_id=7, message_id=10,
            chosen_variant_id="variant_concise",
        )
        db.commit()
        assert first["changed"] is True
        assert first["profile"]["concise_votes"] == 1

        duplicate = service.record_choice(
            db, tenant_id=3, user_id=7, message_id=10,
            chosen_variant_id="variant_concise",
        )
        db.commit()
        assert duplicate["changed"] is False
        assert duplicate["profile"]["concise_votes"] == 1

        changed = service.record_choice(
            db, tenant_id=3, user_id=7, message_id=10,
            chosen_variant_id="variant_detailed",
        )
        db.commit()
        assert changed["changed"] is True
        assert changed["profile"]["concise_votes"] == 0
        assert changed["profile"]["detailed_votes"] == 1
        assert changed["profile"]["preferred_style"] == "detailed_guidance"
        assert db.get(ChatMessage, 10).selected_variant_id == "variant_detailed"
        assert db.get(ChatMessage, 10).content == "详细回答"
        learned = db.query(AgentMemory).filter_by(
            user_id=7, predicate="answer_detail_level", status="active",
        ).one()
        assert learned.value_json == "detailed_guidance"
    finally:
        db.close()
        MySQLBase.metadata.drop_all(engine)
        engine.dispose()
