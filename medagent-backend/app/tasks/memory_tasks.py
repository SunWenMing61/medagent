"""Idempotent maintenance jobs for layered Memory."""

from app.db.session import MySQLSessionLocal
from app.services.memory_service import agent_memory_service


def expire_agent_memory() -> dict[str, int]:
    db = MySQLSessionLocal()
    try:
        count = agent_memory_service.expire(db)
        db.commit()
        return {"expired": count}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
