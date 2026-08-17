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
    ENVIRONMENT: str = "development"
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    REQUIRE_MIGRATIONS: bool = True

    # ==================== PostgreSQL 数据库连接（支持向量搜索） ====================
    DATABASE_URL: str = "postgresql://medagent:${POSTGRES_PASSWORD}@localhost:5432/medagent"     #数据库类型+驱动://用户名:密码@主机:端口/数据库名

    # ==================== MySQL 数据库连接（关系型数据） ====================
    MYSQL_DATABASE_URL: str = "mysql+pymysql://medagent:${MYSQL_PASSWORD}@localhost:3306/medagent"

    # ==================== Redis 连接配置 ====================
    REDIS_URL: str = "redis://localhost:6379/0"
    STANDARD_ANSWER_CACHE_ENABLED: bool = True
    STANDARD_ANSWER_CACHE_TTL_SECONDS: int = 21600
    STANDARD_ANSWER_CACHE_MAX_QUESTION_CHARS: int = 300
    STANDARD_ANSWER_CACHE_LOCK_SECONDS: int = 90
    STANDARD_ANSWER_CACHE_WAIT_MS: int = 1500
    STANDARD_ANSWER_CACHE_VERSION: str = "standard-answer-v3-direct-general"

    # ==================== JWT（JSON Web Token）认证配置 ====================
    SECRET_KEY: str = "change-this-to-a-secure-random-key"   # JWT 签名密钥，生产环境必须更换为安全随机字符串
    JWT_ALGORITHM: str = "HS256"                             # JWT 签名算法，使用 HMAC-SHA256
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440                  # 访问令牌过期时间，默认 1440 分钟（24 小时）

    # ==================== 大语言模型（LLM）配置 ====================
    LLM_API_KEY: Optional[str] = None                        # LLM API 密钥，可选，默认为空
    LLM_API_BASE: str = "https://api.openai.com/v1"          # LLM API 基础地址，默认使用 OpenAI 接口
    LLM_MODEL: str = "gpt-4o-mini"                           # LLM 模型名称
    LLM_ANSWER_GENERATION_ENABLED: bool = True               # 使用模型生成通顺回答；关闭时使用确定性证据摘要降级

    # ==================== 文本嵌入（Embedding）配置 ====================
    EMBEDDING_API_KEY: Optional[str] = None                  # Embedding API 密钥，可选，默认为空
    EMBEDDING_API_BASE: str = "https://api.openai.com/v1/embeddings"  # Embedding API 完整端点
    EMBEDDING_MODEL: str = "text-embedding-3-small"          # Embedding 模型名称，用于向量化文本

    # ==================== RAG（检索增强生成）配置 ====================
    SIMILARITY_THRESHOLD: float = 0.5                         # 相似度阈值，低于此值的文档将被过滤
    RETRIEVAL_CANDIDATE_K: int = 30
    RRF_K: int = 60
    EVIDENCE_MAX_CHUNKS: int = 8
    EVIDENCE_MAX_TOKENS: int = 3000
    CHUNK_SIZE: int = 500                                     # 文档切分时每个块的大小（字符数）
    CHUNK_OVERLAP: int = 100                                  # 文档切分时相邻块之间的重叠字符数
    CHILD_CHUNK_TOKENS: int = 320
    PARENT_CHUNK_TOKENS: int = 900
    CHUNK_OVERLAP_TOKENS: int = 48
    EMBEDDING_DIMENSIONS: int = 1024
    EMBEDDING_VERSION: str = "v1"
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_MAX_RETRIES: int = 3
    EMBEDDING_TIMEOUT_SECONDS: float = 30.0
    EMBEDDING_CACHE_MAX_ENTRIES: int = 5000

    # ==================== 文本清洗与块质量过滤配置 ====================
    MIN_CHUNK_CHARS: int = 15                                 # 块质量过滤——最小字符数，低于此值的块将被丢弃
    MAX_CHUNK_CHARS: int = 2000                               # 块质量过滤——最大字符数，高于此值的块应已在分块阶段处理
    ENABLE_TEXT_CLEANING: bool = True                         # 是否启用文本清洗（Unicode 正规化、全半角转换等）
    REMOVE_URLS: bool = False                                 # 是否在清洗时移除 URL（医疗文档中的 URL 可能有引用价值）

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "./uploads"                             # 上传文件的存储目录
    MAX_UPLOAD_SIZE_MB: int = 50                              # 非 PDF 上传文件的最大大小（MB）；PDF 不限制

    # ==================== 扫描 PDF / OCR ====================
    OCR_LANGUAGES: str = "ch_sim,en"                         # EasyOCR 语言，逗号分隔
    OCR_DPI: int = 144                                        # 扫描页渲染分辨率，兼顾速度和准确率
    OCR_MIN_NATIVE_TEXT_CHARS: int = 40                       # 低于此字符数的页面回退到 OCR
    OCR_MAX_PAGES: int = 500                                  # 防止异常超大 PDF 无限占用 worker
    OCR_USE_GPU: bool = False                                 # 有 CUDA 环境时可显式开启
    PDF_PAGE_CLASSIFICATION_ENABLED: bool = True
    PDF_LAYOUT_ANALYSIS_ENABLED: bool = True
    PDF_TABLE_EXTRACTION_ENABLED: bool = True
    PDF_HEADER_FOOTER_REMOVAL_ENABLED: bool = True
    PDF_WATERMARK_REMOVAL_ENABLED: bool = True
    PDF_CLEANING_VERSION: str = "medical-clean-v3-structured-vision"
    PDF_PARSER_VERSION: str = "pymupdf-layout-v4-structured-vision"
    PDF_VISION_ANALYSIS_ENABLED: bool = True                 # 复杂图表/扫描表格按需多模态分析
    PDF_VISION_API_KEY: Optional[str] = None                 # 留空时优先复用 EMBEDDING_API_KEY，再复用 LLM_API_KEY
    PDF_VISION_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    PDF_VISION_MODEL: str = "qwen3-vl-plus"
    PDF_VISION_MAX_PAGES: int = 0                            # 0=不限制；正数为单文档视觉页上限
    PDF_VISION_DPI: int = 160
    PDF_VISION_MIN_IMAGE_COVERAGE: float = 0.08
    PDF_VISION_MIN_DRAWINGS: int = 12
    PDF_VISION_MAX_OUTPUT_TOKENS: int = 1800
    PDF_VISION_TIMEOUT_SECONDS: float = 90.0
    DOCUMENT_QUALITY_ASSESSMENT_ENABLED: bool = False          # 上传文档清洗后直接向量化，不做质量分级
    OCR_ENABLED: bool = True
    OCR_ENGINE: str = "easyocr"
    OCR_DPI_DEFAULT: int = 180
    OCR_DPI_MAX: int = 300
    OCR_MAX_PIXELS: int = 24_000_000
    OCR_QUALITY_GOOD_THRESHOLD: float = 0.85
    OCR_QUALITY_MANUAL_REVIEW_THRESHOLD: float = 0.65
    OCR_MODEL_DIR: Optional[str] = None
    CHUNK_TOKEN_SIZE: int = 400
    CHUNK_TOKEN_OVERLAP: int = 64
    PARENT_CHUNK_TOKEN_SIZE: int = 1000
    DOCUMENT_PROCESS_TIMEOUT_SECONDS: int = 14400              # RQ 默认 180 秒不足以处理数百页扫描件
    TASK_STALE_AFTER_SECONDS: int = 900                        # 处理中超过 15 分钟无心跳则转为失败
    OUTBOX_DISPATCH_INTERVAL_SECONDS: int = 15                 # Worker 周期性重放尚未成功派发的上传任务
    DOCUMENT_INLINE_FALLBACK_ENABLED: bool = True              # 没有 RQ Worker 时由 API 后台线程自动完成解析和向量化
    DOCUMENT_INLINE_MAX_WORKERS: int = 2                       # 本地兜底处理的最大并发数，避免 OCR/向量化耗尽资源
    DOCUMENT_AUTO_RECOVERY_ENABLED: bool = True                # 启动后自动恢复已解析但尚未完成向量化的文档
    DOCUMENT_PROCESS_MAX_ATTEMPTS: int = 3                     # 瞬时网络错误的整条流水线最大尝试次数；重试会复用解析检查点
    DOCUMENT_RETRY_DELAY_SECONDS: float = 5.0                  # 文档级瞬时错误重试基础等待时间

    # ==================== 网络搜索配置（兼容 Serper.dev API） ====================
    SEARCH_API_KEY: Optional[str] = None                      # 搜索 API 密钥，可选，默认为空
    SEARCH_API_BASE: str = "https://google.serper.dev"        # 搜索 API 基础地址
    ENABLE_GENERAL_WEB_SEARCH: bool = True                    # 通用问答自动并行检索知识库与互联网

    # ==================== 受控多 Agent 运行时 ====================
    AGENT_MAX_CALLS: int = 8
    TOOL_MAX_CALLS: int = 10
    TOOL_DEFAULT_TIMEOUT: float = 8.0
    TOOL_ENABLE_CIRCUIT_BREAKER: bool = True
    TOOL_ENABLE_CACHE: bool = True
    TOOL_ENABLE_TRACING: bool = True
    TOOL_CIRCUIT_FAILURE_THRESHOLD: int = 3
    TOOL_CIRCUIT_RESET_SECONDS: int = 30
    RETRIEVAL_MAX_RETRIES: int = 1
    QUERY_REWRITE_MAX_RETRIES: int = 1
    SAFETY_MAX_REWRITES: int = 1
    AGENT_TOTAL_TIMEOUT_SECONDS: int = 45
    AGENT_TOKEN_BUDGET: int = 6000
    # Hybrid runtime routing thresholds and bounded ReAct budget.  These are
    # environment-configurable so evaluation data can tune them without a
    # business-code release.
    HYBRID_DIRECT_THRESHOLD: float = 0.20
    HYBRID_MULTI_AGENT_THRESHOLD: float = 0.45
    HYBRID_ROUTER_LOW_CONFIDENCE: float = 0.68
    REACT_MAX_STEPS: int = 7
    REACT_MAX_TOOL_CALLS: int = 3
    REACT_MAX_UNIQUE_TOOLS: int = 2
    REACT_MAX_REPEATED_TOOL_CALLS: int = 1
    REACT_MAX_TOOL_FAILURES: int = 2
    REACT_MAX_TOKEN_BUDGET: int = 4000
    REACT_ALLOW_ESCALATION: bool = True
    HYBRID_MINIMAL_AGENT_TEAM: bool = True
    ENABLE_HUMAN_REVIEW: bool = True
    CHECKPOINTER_BACKEND: str = "database"
    CHECKPOINT_TTL: int = 86400
    MEMORY_TTL_DAYS: int = 30
    ENABLE_NEW_MEMORY_ARCHITECTURE: bool = True
    ENABLE_EVIDENCE_VERIFICATION: bool = True
    MEMORY_ENABLED: bool = True
    LONG_TERM_MEMORY_ENABLED: bool = True
    SESSION_MEMORY_BACKEND: str = "sql"
    SESSION_MEMORY_TTL_DAYS: int = 30
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DATABASE: str = "medagent"
    MONGODB_SESSION_COLLECTION: str = "session_memories"
    MONGODB_CONNECT_TIMEOUT_MS: int = 3000
    MONGODB_REQUIRED: bool = False
    MEMORY_SUMMARY_TOKEN_LIMIT: int = 800
    MEMORY_SUMMARY_CHAR_LIMIT: int = 8000
    MEMORY_MAX_ITEMS_PER_AGENT: int = 6
    MEMORY_MAX_TOKENS_PER_AGENT: int = 1200
    MEMORY_DEFAULT_TTL_DAYS: int = 90
    MEMORY_MEDICAL_SENSITIVE_ENABLED: bool = False
    MEMORY_ENCRYPTION_KEY: Optional[str] = None
    MEMORY_RECENCY_HALF_LIFE_DAYS: int = 30
    MEMORY_WEIGHT_QUERY_OVERLAP: float = 0.35
    MEMORY_WEIGHT_TASK: float = 0.25
    MEMORY_WEIGHT_IMPORTANCE: float = 0.20
    MEMORY_WEIGHT_RECENCY: float = 0.10
    MEMORY_WEIGHT_CONFIDENCE: float = 0.10
    RETRIEVAL_PARENT_CHILD_ENABLED: bool = True
    RETRIEVAL_NEIGHBOR_EXPANSION_ENABLED: bool = True
    RETRIEVAL_TIMEOUT_SECONDS: float = 10.0
    RETRIEVAL_EMBEDDING_CACHE_TTL: int = 3600
    RETRIEVAL_TRACE_ENABLED: bool = True
    HNSW_EF_SEARCH: int = 80
    ENABLE_ONLINE_MEDICAL_SEARCH: bool = False
    ENABLE_AGENT_TRACING: bool = True
    DEFAULT_AGENT_MODEL: str = "gpt-4o-mini"
    TRIAGE_MODEL: str = "gpt-4o-mini"
    EVIDENCE_MODEL: str = "gpt-4o-mini"
    ANSWER_MODEL: str = "gpt-4o-mini"
    SAFETY_MODEL: str = "gpt-4o-mini"

    class Config:
        """
        Pydantic 内部配置类。
        指定从 .env 文件读取配置值，编码为 UTF-8。
        """
        env_file = ".env"              # 指定环境变量文件路径
        env_file_encoding = "utf-8"    # 环境变量文件的编码方式


# 创建全局单例配置实例，供整个应用使用
settings = Settings()
