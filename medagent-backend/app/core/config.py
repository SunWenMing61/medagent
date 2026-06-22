# 从 pydantic-settings 库导入 BaseSettings 基类，用于从环境变量/配置文件加载设置
from pydantic_settings import BaseSettings
# 导入 Optional 类型注解，用于声明可选字段（值可以为 None）
from typing import Optional


class Settings(BaseSettings):
    """
    应用全局配置类。
    继承自 BaseSettings，会自动从环境变量或 .env 文件读取配置值。
    """

    # ==================== 应用基本配置 ====================
    APP_NAME: str = "MedAgent"          # 应用名称，默认为 "MedAgent"
    VERSION: str = "1.0.0"              # 应用版本号
    HOST: str = "0.0.0.0"               # 服务监听地址，0.0.0.0 表示监听所有网络接口
    PORT: int = 8000                    # 服务监听端口号

    # ==================== PostgreSQL 数据库连接（支持向量搜索） ====================
    DATABASE_URL: str = "postgresql://medagent:${POSTGRES_PASSWORD}@localhost:5432/medagent"

    # ==================== MySQL 数据库连接（关系型数据） ====================
    MYSQL_DATABASE_URL: str = "mysql+pymysql://medagent:${MYSQL_PASSWORD}@localhost:3306/medagent"

    # ==================== Redis 连接配置 ====================
    REDIS_URL: str = "redis://localhost:6379/0"

    # ==================== JWT（JSON Web Token）认证配置 ====================
    SECRET_KEY: str = "change-this-to-a-secure-random-key"   # JWT 签名密钥，生产环境必须更换为安全随机字符串
    JWT_ALGORITHM: str = "HS256"                             # JWT 签名算法，使用 HMAC-SHA256
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440                  # 访问令牌过期时间，默认 1440 分钟（24 小时）

    # ==================== 大语言模型（LLM）配置 ====================
    LLM_API_KEY: Optional[str] = None                        # LLM API 密钥，可选，默认为空
    LLM_API_BASE: str = "https://api.openai.com/v1"          # LLM API 基础地址，默认使用 OpenAI 接口
    LLM_MODEL: str = "gpt-4o-mini"                           # LLM 模型名称

    # ==================== 文本嵌入（Embedding）配置 ====================
    EMBEDDING_API_KEY: Optional[str] = None                  # Embedding API 密钥，可选，默认为空
    EMBEDDING_API_BASE: str = "https://api.openai.com/v1"    # Embedding API 基础地址
    EMBEDDING_MODEL: str = "text-embedding-3-small"          # Embedding 模型名称，用于向量化文本

    # ==================== RAG（检索增强生成）配置 ====================
    TOP_K: int = 5                                            # 检索时返回的最相似文档数量
    SIMILARITY_THRESHOLD: float = 0.5                         # 相似度阈值，低于此值的文档将被过滤
    CHUNK_SIZE: int = 500                                     # 文档切分时每个块的大小（字符数）
    CHUNK_OVERLAP: int = 100                                  # 文档切分时相邻块之间的重叠字符数

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "./uploads"                             # 上传文件的存储目录
    MAX_UPLOAD_SIZE_MB: int = 50                              # 单个上传文件的最大大小（MB）

    # ==================== 网络搜索配置（兼容 Serper.dev API） ====================
    SEARCH_API_KEY: Optional[str] = None                      # 搜索 API 密钥，可选，默认为空
    SEARCH_API_BASE: str = "https://google.serper.dev"        # 搜索 API 基础地址

    class Config:
        """
        Pydantic 内部配置类。
        指定从 .env 文件读取配置值，编码为 UTF-8。
        """
        env_file = ".env"              # 指定环境变量文件路径
        env_file_encoding = "utf-8"    # 环境变量文件的编码方式


# 创建全局单例配置实例，供整个应用使用
settings = Settings()
