# 从 pydantic 导入 BaseModel（数据模型基类）
from pydantic import BaseModel
# 从 Python 标准库导入 datetime，用于时间戳字段类型
from datetime import datetime
# 从 typing 导入 Optional（可选类型）
from typing import Optional


class UserResponse(BaseModel):
    # 用户信息响应模型，返回用户的基本信息
    # 用户 ID
    id: int
    # 用户名
    username: str
    # 电子邮箱，可为空
    email: Optional[str] = None
    # 用户角色（user 或 admin）
    role: str
    # 用户状态（1=正常，0=禁用）
    status: int
    # 创建时间，可为空
    created_at: Optional[datetime] = None

    class Config:
        # 配置允许从 ORM 属性（SQLAlchemy 模型属性）读取数据
        from_attributes = True


class UserUpdateRequest(BaseModel):
    # 用户信息更新请求模型，所有字段均为可选，只更新传入的字段
    # 用户名，可选
    username: Optional[str] = None
    # 电子邮箱，可选
    email: Optional[str] = None


class AdminUserStatusRequest(BaseModel):
    # 管理员修改用户状态请求模型
    # 目标状态值（1=正常，0=禁用），必填整数
    status: int
