# 从 FastAPI 导入路由和依赖注入
from fastapi import APIRouter, Depends
# 从 SQLAlchemy 导入 ORM 会话类型
from sqlalchemy.orm import Session

# 导入获取当前用户的依赖函数
from app.core.dependencies import get_current_user
# 导入 MySQL 数据库会话获取函数
from app.db.session import get_mysql_db
# 导入用户模型
from app.models.user import User
# 导入用户相关的 Pydantic 请求/响应模型
from app.schemas.user import UserResponse, UserUpdateRequest

# 创建用户路由实例
router = APIRouter()


# 获取个人信息接口：GET /api/users/me，返回 UserResponse 类型
@router.get("/me", response_model=UserResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    # 直接从依赖注入中获取当前已认证用户信息并返回
    return current_user


# 更新个人信息接口：PUT /api/users/me，返回 UserResponse 类型
@router.put("/me", response_model=UserResponse)
def update_profile(
    req: UserUpdateRequest,                       # 用户更新请求体（可选的用户名和邮箱）
    db: Session = Depends(get_mysql_db),          # MySQL 数据库会话
    current_user: User = Depends(get_current_user), # 当前已认证用户
):
    # 如果提供了新用户名，更新当前用户的用户名
    if req.username:
        current_user.username = req.username
    # 如果提供了新邮箱，更新当前用户的邮箱
    if req.email:
        current_user.email = req.email
    # 提交事务，保存更改
    db.commit()
    # 刷新用户对象以获取数据库中的最新状态
    db.refresh(current_user)
    # 返回更新后的用户信息
    return current_user
