# 导入 FastAPI 的 Depends（依赖注入）、HTTPException（HTTP 异常）和 status（HTTP 状态码）模块
from fastapi import Depends, HTTPException, status
# 导入 FastAPI 的 HTTPBearer（Bearer 令牌认证方案）和 HTTPAuthorizationCredentials（认证凭据类型）
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# 导入 SQLAlchemy 的 Session 类型，用于类型注解
from sqlalchemy.orm import Session

# 导入自定义的 JWT 令牌解码函数
from app.core.security import decode_access_token
# 导入获取 MySQL 数据库会话的依赖函数
from app.db.session import get_mysql_db
# 导入 User 模型类，用于数据库查询
from app.models.user import User

# 创建 HTTP Bearer 认证方案实例
# 自动从请求头中提取 Authorization: Bearer <token> 中的令牌
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),  # 从请求头中自动提取 Bearer 令牌
    db: Session = Depends(get_mysql_db),                            # 自动获取 MySQL 数据库会话
) -> User:
    """
    核心依赖：获取当前已认证的活跃用户。

    处理流程：
    1. 从认证凭据中提取 JWT 令牌字符串
    2. 解码令牌，验证签名和有效期
    3. 从令牌载荷中提取用户 ID（sub 字段）
    4. 在数据库中查询该 ID 且状态为启用（status=1）的用户
    5. 如果任一环节失败，抛出 HTTP 401 未授权异常

    参数:
        credentials (HTTPAuthorizationCredentials): FastAPI 自动注入的 Bearer 令牌凭据
        db (Session): FastAPI 自动注入的 MySQL 数据库会话

    返回:
        User: 查询到的活跃用户对象

    异常:
        HTTPException 401: 令牌无效/过期/用户不存在或被禁用
    """
    token = credentials.credentials               # 提取 Bearer 令牌中的 JWT 字符串
    payload = decode_access_token(token)          # 解码 JWT，验证签名和有效期
    if payload is None:                           # 如果解码返回 None，说明令牌无效或已过期
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,  # 返回 401 状态码
            detail="Invalid or expired token",          # 错误详情：令牌无效或已过期
        )
    sub = payload.get("sub")                      # 从 JWT 载荷中提取 "sub"（subject，用户标识）字段
    if sub is None:                               # 如果载荷中没有 sub 字段，说明令牌格式异常
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",              # 错误详情：令牌载荷无效
        )
    user_id = int(sub)                            # 将 sub 转换为整数类型的用户 ID
    user = db.query(User).filter(User.id == user_id, User.status == 1).first()  # 查询 ID 匹配且状态为启用（1）的用户
    if user is None:                              # 如果未找到用户或该用户已被禁用
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or disabled",         # 错误详情：用户不存在或已被禁用
        )
    return user                                   # 返回已认证的当前用户对象


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """
    权限校验依赖：要求当前用户具有管理员角色。

    处理流程：
    1. 首先通过 get_current_user 依赖获取已认证用户
    2. 检查用户的 role 字段是否为 "admin"
    3. 如果不是管理员，抛出 HTTP 403 禁止访问异常

    参数:
        current_user (User): 由 get_current_user 依赖注入的当前认证用户

    返回:
        User: 确认具有管理员权限的用户对象

    异常:
        HTTPException 403: 当前用户非管理员角色
    """
    if current_user.role != "admin":              # 检查用户角色是否为 "admin"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,       # 返回 403 状态码（禁止访问）
            detail="Admin privileges required",          # 错误详情：需要管理员权限
        )
    return current_user                           # 权限校验通过，返回当前用户
