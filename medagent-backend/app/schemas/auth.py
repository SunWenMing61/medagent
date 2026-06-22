# 从 pydantic 导入 BaseModel（数据模型基类）和 Field（字段验证与元数据）
from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    # 注册请求模型，用于用户注册接口的请求体验证
    # 用户名，必填，长度限制 2~100 字符
    username: str = Field(..., min_length=2, max_length=100)
    # 密码，必填，长度限制 6~255 字符
    password: str = Field(..., min_length=6, max_length=255)
    # 电子邮箱，非必填，默认为空字符串
    email: str = Field(default="")


class LoginRequest(BaseModel):
    # 登录请求模型，用于用户登录接口的请求体验证
    # 用户名，必填字符串
    username: str
    # 密码，必填字符串
    password: str


class TokenResponse(BaseModel):
    # 令牌响应模型，登录成功后返回的认证令牌信息
    # JWT 访问令牌字符串
    access_token: str
    # 令牌类型，默认值为 "bearer"（Bearer Token 认证方式）
    token_type: str = "bearer"
    # 登录用户 ID
    user_id: int
    # 登录用户名
    username: str
    # 用户角色，如 "user" 或 "admin"
    role: str


class AuthMeResponse(BaseModel):
    # 当前用户信息响应模型，用于 /auth/me 接口返回用户信息
    # 用户 ID
    id: int
    # 用户名
    username: str
    # 电子邮箱
    email: str
    # 用户角色
    role: str
    # 用户状态（1=正常，0=禁用）
    status: int
