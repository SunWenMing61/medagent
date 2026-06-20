import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1.router import router
from app.db.base import Base, MySQLBase
from app.db.session import pg_engine, mysql_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup: create tables in both databases (for development; use Alembic in production)
    try:
        # PostgreSQL tables (document_chunk with pgvector)
        Base.metadata.create_all(bind=pg_engine)
        # MySQL tables (all relational models)
        MySQLBase.metadata.create_all(bind=mysql_engine)
        _add_kb_ids_column()
        _init_default_data()
    except Exception as e:
        print(f"Database initialization warning: {e}")

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    yield

    # Shutdown
    pass


def _init_default_data():
    """Initialize default admin user and model config if not exists."""
    from sqlalchemy.orm import Session
    from app.db.session import MySQLSessionLocal
    from app.models.user import User
    from app.models.model_config import ModelConfig
    from app.core.security import hash_password
    from app.services.chat_history_service import get_or_create_chat_history_kb

    db: Session = MySQLSessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if not admin:
            admin = User(
                username="admin",
                password_hash=hash_password(os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")),
                email="admin@medagent.com",
                role="admin",
                status=1,
            )
            db.add(admin)

        config = db.query(ModelConfig).first()
        if not config:
            config = ModelConfig(
                llm_model=settings.LLM_MODEL,
                embedding_model=settings.EMBEDDING_MODEL,
                top_k=settings.TOP_K,
                similarity_threshold=settings.SIMILARITY_THRESHOLD,
                temperature=0.7,
                max_tokens=2048,
            )
            db.add(config)

        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()

    # Ensure the global chat history KB exists
    try:
        get_or_create_chat_history_kb()
    except Exception:
        pass


def _add_kb_ids_column():
    """Add kb_ids_json column to chat_session if missing (idempotent)."""
    from sqlalchemy import text
    from app.db.session import mysql_engine
    try:
        with mysql_engine.connect() as conn:
            conn.execute(
                text("ALTER TABLE chat_session ADD COLUMN kb_ids_json TEXT NULL AFTER summary")
            )
            conn.commit()
    except Exception:
        pass  # column already exists or table doesn't exist


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(router)


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.VERSION}
