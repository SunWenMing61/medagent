"""API 端点测试 —— 使用 FastAPI TestClient。"""

# 导入 pytest 测试框架
import pytest
# 导入 FastAPI 测试客户端，用于发送 HTTP 请求
from fastapi.testclient import TestClient

# 导入 FastAPI 应用实例
from app.main import app
# 导入 MySQL 数据库会话工厂和引擎
from app.db.session import MySQLSessionLocal, mysql_engine
# 导入 MySQL ORM 基类（用于创建表）
from app.db.base import MySQLBase
# 导入密码哈希函数
from app.core.security import hash_password
# 导入用户模型
from app.models.user import User


# 测试夹具（fixture）：模块级别，在整个模块中只执行一次
@pytest.fixture(scope="module")
def client():
    """创建测试数据库表结构，初始化测试用户，返回测试客户端。"""
    # 在测试数据库中创建所有表（基于 MySQL 引擎）
    MySQLBase.metadata.create_all(bind=mysql_engine)
    # 获取数据库会话
    db = MySQLSessionLocal()
    # 检查测试用户是否已存在，如果不存在则创建
    if not db.query(User).filter(User.username == "testuser").first():
        user = User(
            username="testuser",                              # 测试用户名
            password_hash=hash_password("test123456"),        # 测试密码（哈希后）
            email="test@test.com",                            # 测试邮箱
            role="user",                                      # 角色为普通用户
            status=1,                                         # 状态为启用
        )
        db.add(user)
        db.commit()
    db.close()
    # 返回 FastAPI 测试客户端实例
    return TestClient(app)


# 认证 API 测试类
class TestAuthAPI:
    """用户注册、登录和身份验证相关测试。"""

    def test_register(self, client):
        """测试用户注册接口：发送注册请求，验证返回成功。"""
        resp = client.post("/api/auth/register", json={
            "username": f"newuser",
            "password": "test123456",
            "email": "new@test.com",
        })
        # 预期状态码为 200
        assert resp.status_code == 200
        # 验证响应消息
        assert resp.json()["message"] == "Registration successful"

    def test_register_duplicate(self, client):
        """测试重复注册：使用已存在的用户名，预期返回 400 错误。"""
        resp = client.post("/api/auth/register", json={
            "username": "testuser",
            "password": "test123456",
        })
        # 预期状态码为 400（用户名已存在）
        assert resp.status_code == 400

    def test_login(self, client):
        """测试用户登录接口：使用正确凭据登录，验证返回 token。"""
        resp = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "test123456",
        })
        # 预期状态码为 200
        assert resp.status_code == 200
        data = resp.json()
        # 验证响应中包含访问令牌
        assert "access_token" in data
        # 验证令牌类型为 Bearer
        assert data["token_type"] == "bearer"

    def test_login_invalid(self, client):
        """测试登录失败：使用错误密码，预期返回 401 错误。"""
        resp = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "wrongpass",
        })
        # 预期状态码为 401（认证失败）
        assert resp.status_code == 401

    def test_me_unauthorized(self, client):
        """测试未授权访问 /me 接口：未提供 token，预期返回 403。"""
        resp = client.get("/api/auth/me")
        # 预期状态码为 403（禁止访问）
        assert resp.status_code == 403

    def test_me_authorized(self, client):
        """测试已授权访问 /me 接口：先登录获取 token，再访问个人资料。"""
        # 先登录获取 token
        login_resp = client.post("/api/auth/login", json={
            "username": "testuser",
            "password": "test123456",
        })
        token = login_resp.json()["access_token"]
        # 使用 Bearer token 访问 /me 接口
        resp = client.get("/api/auth/me", headers={
            "Authorization": f"Bearer {token}"
        })
        # 预期状态码为 200
        assert resp.status_code == 200
        # 验证返回的用户名与测试用户一致
        assert resp.json()["username"] == "testuser"


# 健康检查 API 测试类
class TestHealthAPI:
    """系统健康检查接口测试。"""

    def test_health_check(self, client):
        """测试健康检查接口：验证返回状态为 ok。"""
        resp = client.get("/health")
        # 预期状态码为 200
        assert resp.status_code == 200
        # 验证响应中的状态字段
        assert resp.json()["status"] == "ok"
