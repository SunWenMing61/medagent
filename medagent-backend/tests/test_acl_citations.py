"""Cross-user KB authorization and server citation validation tests."""

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase
from app.services.access_control_service import (
    KnowledgeBaseAccessDenied,
    list_accessible_kb_ids,
    resolve_authorized_kb_ids,
)
from app.services.citation_service import issue_evidence_ids, validate_citations


@pytest.fixture()
def acl_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    KnowledgeBase.__table__.create(engine)
    with Session(engine) as db:
        db.add_all([
            KnowledgeBase(id=1, name="owner private", owner_id=10, visibility="private", status=1),
            KnowledgeBase(id=2, name="other private", owner_id=20, visibility="private", status=1),
            KnowledgeBase(id=3, name="public", owner_id=20, visibility="public", status=1),
            KnowledgeBase(id=4, name="disabled public", owner_id=20, visibility="public", status=0),
        ])
        db.commit()
        yield db


def test_regular_user_only_sees_owned_and_active_public(acl_db):
    user = SimpleNamespace(id=10, role="user")
    assert list_accessible_kb_ids(user, acl_db) == [1, 3]
    assert resolve_authorized_kb_ids(user, [3, 1, 3], acl_db) == [3, 1]
    with pytest.raises(KnowledgeBaseAccessDenied):
        resolve_authorized_kb_ids(user, [2], acl_db)
    with pytest.raises(KnowledgeBaseAccessDenied):
        resolve_authorized_kb_ids(user, [4], acl_db)


def test_admin_sees_all_active_but_not_disabled(acl_db):
    admin = SimpleNamespace(id=99, role="admin")
    assert list_accessible_kb_ids(admin, acl_db) == [1, 2, 3]


def test_explicit_empty_scope_stays_empty(acl_db):
    user = SimpleNamespace(id=10, role="user")
    assert resolve_authorized_kb_ids(user, [], acl_db) == []


def test_citations_only_resolve_to_server_issued_evidence():
    evidence = issue_evidence_ids([
        {"id": 7, "document_id": 11, "kb_id": 3, "content": "verified"},
        {"id": 8, "document_id": 12, "kb_id": 3, "content": "unused"},
    ])
    valid_id = evidence[0]["evidence_id"]
    answer = f"Claim [{valid_id}] and fabricated [ev_0000000000000000]."
    result = validate_citations(answer, evidence)

    assert [item["id"] for item in result.references] == [7]
    assert result.invalid_ids == ["ev_0000000000000000"]
    assert "ev_0000000000000000" not in result.answer


def test_uncited_evidence_is_not_returned_as_if_it_supported_answer():
    evidence = issue_evidence_ids([
        {"id": 1, "document_id": 2, "kb_id": 3, "content": "text"}
    ])
    result = validate_citations("Answer without a citation.", evidence)
    assert result.references == []
