"""Pluggable persistence for the short-lived, multi-turn session memory layer."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.memory import AgentSession


class SessionMemoryRepository(Protocol):
    backend_name: str

    def load(self, db: Session, *, tenant_id: int, user_id: int, thread_id: str) -> dict[str, Any] | None: ...

    def save(self, db: Session, record: dict[str, Any]) -> dict[str, Any]: ...

    def health(self) -> dict[str, Any]: ...


class SqlSessionMemoryRepository:
    backend_name = "sql"

    def load(self, db: Session, *, tenant_id: int, user_id: int, thread_id: str) -> dict[str, Any] | None:
        row = db.query(AgentSession).filter_by(
            tenant_id=tenant_id, user_id=user_id, thread_id=thread_id,
        ).first()
        return self._to_record(row) if row else None

    def save(self, db: Session, record: dict[str, Any]) -> dict[str, Any]:
        row = db.query(AgentSession).filter_by(
            tenant_id=record["tenant_id"], user_id=record["user_id"], thread_id=record["thread_id"],
        ).first()
        if not row:
            row = AgentSession(
                id=record.get("id") or f"ses_{uuid4().hex}",
                tenant_id=record["tenant_id"],
                user_id=record["user_id"],
                thread_id=record["thread_id"],
            )
            db.add(row)
        row.rolling_summary = record.get("rolling_summary", "")
        row.active_topic = record.get("active_topic")
        row.active_entities_json = record.get("active_entities", [])
        row.unresolved_questions_json = record.get("unresolved_questions", [])
        row.confirmed_constraints_json = record.get("confirmed_constraints", [])
        row.latest_corrections_json = record.get("latest_corrections", [])
        db.flush()
        return self._to_record(row)

    @staticmethod
    def _to_record(row: AgentSession) -> dict[str, Any]:
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "user_id": row.user_id,
            "thread_id": row.thread_id,
            "rolling_summary": row.rolling_summary or "",
            "active_topic": row.active_topic,
            "active_entities": row.active_entities_json or [],
            "unresolved_questions": row.unresolved_questions_json or [],
            "confirmed_constraints": row.confirmed_constraints_json or [],
            "latest_corrections": row.latest_corrections_json or [],
            "created_at": row.created_at,
            "updated_at": row.updated_at or row.created_at,
        }

    def health(self) -> dict[str, Any]:
        return {"status": "ready", "backend": self.backend_name}


class MongoSessionMemoryRepository:
    backend_name = "mongodb"

    def __init__(self) -> None:
        self._client = None
        self._collection = None

    def _get_collection(self):
        if self._collection is not None:
            return self._collection
        from pymongo import ASCENDING, MongoClient

        self._client = MongoClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=max(500, int(settings.MONGODB_CONNECT_TIMEOUT_MS)),
            tz_aware=True,
        )
        collection = self._client[settings.MONGODB_DATABASE][settings.MONGODB_SESSION_COLLECTION]
        collection.create_index(
            [("tenant_id", ASCENDING), ("user_id", ASCENDING), ("thread_id", ASCENDING)],
            unique=True,
            name="uq_session_owner_thread",
        )
        collection.create_index("expires_at", expireAfterSeconds=0, name="ttl_session_memory")
        self._collection = collection
        return collection

    def load(self, db: Session, *, tenant_id: int, user_id: int, thread_id: str) -> dict[str, Any] | None:
        del db
        record = self._get_collection().find_one(
            {"tenant_id": tenant_id, "user_id": user_id, "thread_id": thread_id},
            {"_id": False},
        )
        return record

    def save(self, db: Session, record: dict[str, Any]) -> dict[str, Any]:
        del db
        now = datetime.now(timezone.utc)
        payload = dict(record)
        payload.pop("recent_messages", None)
        payload.setdefault("id", f"ses_{uuid4().hex}")
        payload.setdefault("created_at", now)
        payload["updated_at"] = now
        payload["expires_at"] = now + timedelta(days=max(1, settings.SESSION_MEMORY_TTL_DAYS))
        key = {
            "tenant_id": payload["tenant_id"],
            "user_id": payload["user_id"],
            "thread_id": payload["thread_id"],
        }
        self._get_collection().replace_one(key, payload, upsert=True)
        return payload

    def health(self) -> dict[str, Any]:
        assert self._client is not None or self._get_collection() is not None
        self._client.admin.command("ping")
        return {"status": "ready", "backend": self.backend_name}
