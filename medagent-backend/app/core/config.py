from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "MedAgent"
    VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database - PostgreSQL (vector search)
    DATABASE_URL: str = "postgresql://medagent:${POSTGRES_PASSWORD}@localhost:5432/medagent"

    # Database - MySQL (relational data)
    MYSQL_DATABASE_URL: str = "mysql+pymysql://medagent:${MYSQL_PASSWORD}@localhost:3306/medagent"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change-this-to-a-secure-random-key"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # LLM
    LLM_API_KEY: Optional[str] = None
    LLM_API_BASE: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"

    # Embedding
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_API_BASE: str = "https://api.openai.com/v1"
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # RAG
    TOP_K: int = 5
    SIMILARITY_THRESHOLD: float = 0.5
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 100

    # Upload
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 50

    # Web Search (Serper.dev compatible API)
    SEARCH_API_KEY: Optional[str] = None
    SEARCH_API_BASE: str = "https://google.serper.dev"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
