# 导入 datetime 模块中的 datetime（日期时间）、timedelta（时间间隔）和 timezone（时区）类
from datetime import datetime, timedelta, timezone
# 导入 Optional 类型注解，用于声明可能为 None 的返回值
from typing import Optional

# 从 jose 库导入 JWTError（JWT 异常类）和 jwt（JWT 编解码工具）
from jose import JWTError, jwt
# 从 passlib 库导入 CryptContext，用于密码哈希和验证
from passlib.context import CryptContext

# 导入应用配置类，读取 JWT 和密码相关的配置项
from app.core.config import settings

# 创建密码加密上下文对象
# schemes=["bcrypt"] 指定使用 bcrypt 哈希算法对密码进行加密
# deprecated="auto" 表示自动处理已弃用的哈希方案（自动升级旧哈希）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    对明文密码进行哈希加密。

    参数:
        password (str): 用户输入的明文密码

    返回:
        str: 加密后的哈希字符串（包含盐值，可直接存入数据库）
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否与哈希值匹配。

    参数:
        plain_password (str): 用户输入的待验证明文密码
        hashed_password (str): 数据库中存储的哈希密码

    返回:
        bool: 密码匹配返回 True，否则返回 False
    """
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT 访问令牌（access token）。

    逻辑说明：
    1. 复制传入的数据字典（避免修改原始数据）
    2. 计算令牌过期时间：当前 UTC 时间 + 指定的过期时间间隔（或使用默认的 24 小时）
    3. 将过期时间更新到数据字典中（键名为 "exp"）
    4. 使用配置中的密钥和算法对数据进行 JWT 编码签名

    参数:
        data (dict): 要编码到令牌中的载荷数据（如用户 ID）
        expires_delta (Optional[timedelta]): 自定义过期时间间隔，可选

    返回:
        str: 编码后的 JWT 字符串
    """
    to_encode = data.copy()                                   # 复制数据，避免修改原始字典
    expire = datetime.now(timezone.utc) + (                    # 计算过期时间：当前 UTC 时间 +
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)  # 指定的过期时间或默认 24 小时
    )
    to_encode.update({"exp": expire})                         # 将过期时间戳加入 JWT 载荷
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)  # 编码并签名生成 JWT


def decode_access_token(token: str) -> Optional[dict]:
    """
    解码并验证 JWT 访问令牌。

    逻辑说明：
    1. 尝试使用配置的密钥和算法对令牌进行解码
    2. 如果解码成功，返回载荷中的原始数据（字典形式）
    3. 如果令牌无效、过期或签名不匹配，捕获 JWTError 异常并返回 None

    参数:
        token (str): 待解码的 JWT 字符串

    返回:
        Optional[dict]: 解码成功返回载荷字典，失败返回 None
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]  # 使用密钥和指定算法解码
        )
        return payload                                    # 解码成功，返回载荷数据
    except JWTError:
        return None                                       # 解码失败（令牌无效/过期/签名错误），返回 None
