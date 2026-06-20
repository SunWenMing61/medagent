"""Tests for API endpoints using FastAPI TestClient."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db.session import MySQLSessionLocal, mysql_engine
from app.db.base import MySQLBase
from app.core.security import hash_password
from app.models.user import User


@pytest.fixture(scope="module")
def client():
    MySQLBase.metadata.create_all(bind=mysql_engine)
    db = MySQLSessionLocal()
    if not db.query(User).filter(User.username == "testuser").first():
        user = User(
            username="testuser",
            password_hash=hash_password("test123456"),
            email="test@test.com",
            role="user",
            status=1,
        )
        db.add(user)
        db.commit()
    db.close()
    return TestClient(app)


class TestAuthAPI:
    def test_register(self, client):
        resp = client.post("/api/auth/register", json={
            "username": f"newuser",
            "password": "test123456",
            "email": "new@test.com",
        })
        assert resp.status_code == 200
        assert resp.json()["message"] == "Registration successful"

    def test_register_duplicate(self, client):
        resp = client.post("/api/auth/register", json={
            "username": "testuser",
            "password": "test123456",
        })
        assert resp.status_code == 400

    def test_login(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "test123456",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_login_invalid(self, client):
        resp = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "wrongpass",
        })
        assert resp.status_code == 401

    def test_me_unauthorized(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 403

    def test_me_authorized(self, client):
        login_resp = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "test123456",
        })
        token = login_resp.json()["access_token"]
        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        assert resp.status_code == 200
        assert resp.json()["username"] == "testuser"


class TestHealthAPI:
    def test_health_check(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
