"""API integration tests using an isolated in-memory application database."""

import random

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 - register every MySQL model before create_all
from app.core.dependencies import _rate_limiter
from app.core.security import hash_password
from app.db.base import MySQLBase
from app.db.session import get_mysql_db
from app.main import app
from app.models.user import User
from app.graphs.graph_state import new_agent_state
from app.services.agent_run_service import agent_run_service


@compiles(BigInteger, "sqlite")
def _sqlite_big_integer(_type, _compiler, **_kwargs):
    return "INTEGER"


@pytest.fixture(scope="module")
def db_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    MySQLBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = factory()
    db.add(User(
        id=1,
        tenant_id=1,
        username="testuser",
        password_hash=hash_password("test123456"),
        email="test@test.com",
        role="user",
        status=1,
    ))
    db.commit()
    db.close()
    yield factory
    MySQLBase.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="module")
def client(db_factory):
    def override_db():
        db = db_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_mysql_db] = override_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.pop(get_mysql_db, None)


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    with _rate_limiter._lock:
        _rate_limiter._windows.clear()


def _login(client: TestClient) -> str:
    response = client.post("/api/auth/login", json={
        "username": "testuser", "password": "test123456",
    })
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


class TestAuthAPI:
    def test_register(self, client):
        response = client.post("/api/auth/register", json={
            "username": f"newuser_{random.randint(10000, 99999)}",
            "password": "test123456",
            "email": "new@test.com",
        })
        assert response.status_code == 200
        assert response.json()["message"] == "Registration successful"

    def test_register_duplicate(self, client):
        response = client.post("/api/auth/register", json={
            "username": "testuser", "password": "test123456",
        })
        assert response.status_code == 400

    def test_login(self, client):
        token = _login(client)
        assert token

    def test_login_invalid(self, client):
        response = client.post("/api/auth/login", json={
            "username": "testuser", "password": "wrongpass",
        })
        assert response.status_code == 401

    def test_me_unauthorized(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_me_authorized(self, client):
        response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {_login(client)}"})
        assert response.status_code == 200
        assert response.json()["username"] == "testuser"

    def test_logout(self, client):
        response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {_login(client)}"})
        assert response.status_code == 200

    def test_login_disabled_account(self, client, db_factory):
        db = db_factory()
        user = db.query(User).filter(User.username == "testuser").one()
        user.status = 0
        db.commit()
        db.close()
        try:
            response = client.post("/api/auth/login", json={
                "username": "testuser", "password": "test123456",
            })
            assert response.status_code == 403
        finally:
            db = db_factory()
            db.query(User).filter(User.username == "testuser").update({"status": 1})
            db.commit()
            db.close()


class TestAgentRunsAPI:
    def test_create_agent_run_contract(self, client, monkeypatch):
        state = new_agent_state(
            raw_query="What is blood pressure?",
            user_id=1,
            tenant_id=1,
            authorized_kb_ids=[],
            thread_id="api-agent-test",
        )
        state.update(
            status="completed",
            current_agent="finalize",
            intent="medical_knowledge",
            evidence_status="insufficient",
            final_answer="No verified evidence was available.",
        )
        monkeypatch.setattr(agent_run_service, "start", lambda **_kwargs: state)
        token = _login(client)
        response = client.post(
            "/api/agent-runs",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": "What is blood pressure?", "kb_ids": [], "thread_id": "api-agent-test"},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["request_id"] == state["request_id"]
        assert payload["status"] == "completed"
        assert payload["current_node"] == "finalize"


class TestKnowledgeBaseAPI:
    def test_list_knowledge_bases(self, client):
        response = client.get("/api/kb", headers={"Authorization": f"Bearer {_login(client)}"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_create_knowledge_base(self, client):
        response = client.post(
            "/api/kb",
            headers={"Authorization": f"Bearer {_login(client)}"},
            json={
                "name": "测试知识库",
                "description": "用于 API 测试的知识库",
                "type": "general",
                "visibility": "public",
            },
        )
        assert response.status_code in (200, 201)

    def test_unauthorized_access(self, client):
        assert client.get("/api/kb").status_code == 401


class TestDocumentAPI:
    def test_list_documents(self, client):
        response = client.get(
            "/api/documents", headers={"Authorization": f"Bearer {_login(client)}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestSessionAPI:
    def test_list_sessions(self, client):
        response = client.get(
            "/api/chat/sessions", headers={"Authorization": f"Bearer {_login(client)}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_list_sessions_by_type(self, client):
        response = client.get(
            "/api/chat/sessions?type=qa", headers={"Authorization": f"Bearer {_login(client)}"}
        )
        assert response.status_code == 200


class TestHealthAPI:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert "service" in response.json()
        assert "version" in response.json()
