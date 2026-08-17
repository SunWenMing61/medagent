"""FastAPI application bootstrap with fail-fast production checks."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis
from rq import Queue, Worker
from sqlalchemy import text

from app.api.v1.router import router
from app.api.v1.ws import router as ws_router
from app.core.config import settings
from app.db.session import mysql_engine, pg_engine
from app.core.observability import RequestContextMiddleware, configure_logging
from app.services.document_runtime_service import document_runtime_service
from app.services.memory_service import session_memory_service


EXPECTED_SCHEMA_REVISION = "0011_hybrid_eval"


def _validate_security_config() -> None:
    production = settings.ENVIRONMENT.lower() in {"production", "prod"}
    insecure_secrets = {
        "change-this-to-a-secure-random-key",
        "change-this-in-production",
        "",
    }
    if production and settings.SECRET_KEY in insecure_secrets:
        raise RuntimeError("Production SECRET_KEY must be set to a strong non-default value")
    origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
    if production and "*" in origins:
        raise RuntimeError("Wildcard CORS is forbidden in production")


def _verify_migrations() -> None:
    if not settings.REQUIRE_MIGRATIONS:
        return
    for name, engine in (("postgres", pg_engine), ("mysql", mysql_engine)):
        try:
            with engine.connect() as connection:
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        except Exception as exc:
            raise RuntimeError(
                f"{name} schema is not migration-ready; run Alembic before starting the API: {exc}"
            ) from exc
        if not revision:
            raise RuntimeError(f"{name} alembic_version is empty")
        if revision != EXPECTED_SCHEMA_REVISION:
            raise RuntimeError(
                f"{name} schema revision is {revision}, expected {EXPECTED_SCHEMA_REVISION}; "
                "run Alembic upgrade head before starting the API"
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    del app
    _validate_security_config()
    _verify_migrations()
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    document_runtime_service.start()
    try:
        yield
    finally:
        document_runtime_service.stop()


configure_logging()
app = FastAPI(title=settings.APP_NAME, version=settings.VERSION, lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)

cors_origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)
app.include_router(router)
app.include_router(ws_router, prefix="/api")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.VERSION}


@app.get("/health/ready")
def readiness_check():
    for engine in (pg_engine, mysql_engine):
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    memory = session_memory_service.health()
    if settings.MONGODB_REQUIRED and memory.get("status") != "ready":
        raise RuntimeError(f"Required session-memory backend is unavailable: {memory.get('detail', 'unknown')}")
    return {"status": "ready", "session_memory": memory}


@app.get("/health/session-memory")
def session_memory_health():
    return session_memory_service.health()


@app.get("/health/document-processing")
def document_processing_health():
    """单独报告上传处理链路，便于发现“队列有任务但没有 Worker”。"""
    redis_connection = Redis.from_url(settings.REDIS_URL)
    redis_connection.ping()
    queue = Queue("default", connection=redis_connection)
    workers = Worker.all(connection=redis_connection)
    active_workers = [
        {"name": worker.name, "state": worker.state}
        for worker in workers
        if worker.state in {"idle", "busy", "started"}
    ]
    inline_fallback = bool(settings.DOCUMENT_INLINE_FALLBACK_ENABLED)
    return {
        "status": "ready" if active_workers or inline_fallback else "degraded",
        "queue": "default",
        "queued_jobs": queue.count,
        "active_worker_count": len(active_workers),
        "workers": active_workers,
        "inline_fallback_enabled": inline_fallback,
        "processing_mode": "rq_worker" if active_workers else (
            "api_background_fallback" if inline_fallback else "unavailable"
        ),
    }
