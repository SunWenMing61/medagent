# 从 FastAPI 导入路由分组、依赖注入、HTTP 异常类
from fastapi import APIRouter, Depends, HTTPException
# 从 SQLAlchemy 导入 ORM 会话类型，用于数据库操作
from sqlalchemy.orm import Session

# 从安全模块导入密码哈希、验证和 JWT 令牌生成函数
from app.core.security import hash_password, verify_password, create_access_token
# 从依赖模块导入获取当前登录用户的依赖函数
from app.core.dependencies import get_current_user
# 从数据库会话模块导入获取 MySQL 数据库会话的函数
from app.db.session import get_mysql_db
# 导入用户模型，用于 ORM 查询
from app.models.user import User
# 导入认证相关的 Pydantic 请求/响应模型
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, AuthMeResponse
# 导入通用消息响应模型
from app.schemas.common import MessageResponse

# 创建认证路由实例
router = APIRouter()


# 注册接口：POST /api/auth/register，返回 MessageResponse 类型
@router.post("/register", response_model=MessageResponse)
def register(req: RegisterRequest, db: Session = Depends(get_mysql_db)):
    # 查询数据库中是否已存在同名的用户
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        # 如果用户名已存在，返回 400 错误
        raise HTTPException(status_code=400, detail="Username already exists")
    # 创建新的用户对象，使用哈希后的密码
    user = User(
        username=req.username,               # 用户名
        password_hash=hash_password(req.password),  # 密码经过哈希处理
        email=req.email or "",                # 邮箱，可选，默认为空字符串
        role="user",                          # 默认角色为普通用户
        status=1,                             # 状态为启用（1=启用）
    )
    # 将新用户添加到数据库会话
    db.add(user)
    # 提交事务，将用户写入数据库
    db.commit()
    # 返回注册成功的消息
    return {"message": "Registration successful"}


# 登录接口：POST /api/auth/login，返回 TokenResponse 类型
@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, db: Session = Depends(get_mysql_db)):
    # 根据用户名查询用户
    user = db.query(User).filter(User.username == req.username).first()
    # 如果用户不存在或密码不匹配，返回 401 未授权错误
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    # 检查用户状态是否为禁用（status != 1 表示禁用）
    if user.status != 1:
        raise HTTPException(status_code=403, detail="Account is disabled")
    # 生成 JWT 访问令牌，包含用户 ID 和角色信息
    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    # 返回令牌和用户基本信息
    return TokenResponse(
        access_token=token,       # JWT 访问令牌
        user_id=user.id,          # 用户 ID
        username=user.username,   # 用户名
        role=user.role,           # 用户角色
    )


# 登出接口：POST /api/auth/logout，返回 MessageResponse 类型
@router.post("/logout", response_model=MessageResponse)
def logout(current_user: User = Depends(get_current_user)):
    # 当前版本的无状态 JWT 登出仅返回成功消息
    # 实际令牌失效需要客户端丢弃令牌
    return {"message": "Logged out successfully"}


# 获取当前用户信息接口：GET /api/auth/me，返回 AuthMeResponse 类型
@router.get("/me", response_model=AuthMeResponse)
def get_me(current_user: User = Depends(get_current_user)):
    # 从依赖注入获取当前已认证用户，返回用户基本信息
    return AuthMeResponse(
        id=current_user.id,          # 用户 ID
        username=current_user.username,  # 用户名
        email=current_user.email or "",   # 邮箱，默认为空
        role=current_user.role,      # 用户角色
        status=current_user.status,  # 用户状态
    )
