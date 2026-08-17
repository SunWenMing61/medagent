"""Transactional outbox for durable document-task dispatch."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.session import MySQLSessionLocal
from app.models.task_outbox import TaskOutbox
from app.models.document import Document


def add_document_outbox(
    db: Session, document_id: int, user_id: int, content_sha256: str
) -> TaskOutbox:
    key = f"document.process:{document_id}:{content_sha256}"
    existing = db.query(TaskOutbox).filter(TaskOutbox.idempotency_key == key).first()
    if existing:
        return existing
    event = TaskOutbox(
        event_type="document.process",
        idempotency_key=key,
        payload={"document_id": document_id, "user_id": user_id},
        status="pending",
    )
    db.add(event)
    return event


def dispatch_outbox_event(outbox_id: int) -> str:
    from app.tasks.document_tasks import enqueue_document

    db = MySQLSessionLocal()
    try:
        event = db.query(TaskOutbox).filter(TaskOutbox.id == outbox_id).with_for_update().first()
        if not event:
            raise ValueError("Outbox event not found")
        if event.status == "dispatched" and event.task_id:
            return event.task_id
        event.attempts = int(event.attempts or 0) + 1
        try:
            task_id = enqueue_document(
                int(event.payload["document_id"]),
                int(event.payload["user_id"]),
                idempotency_key=event.idempotency_key,
            )
        except Exception as exc:
            event.status = "pending"
            event.last_error = str(exc)[:2000]
            db.commit()
            raise
        event.status = "dispatched"
        event.task_id = task_id
        event.last_error = None
        event.dispatched_at = datetime.now(timezone.utc).replace(tzinfo=None)
        document = db.query(Document).filter(Document.id == int(event.payload["document_id"])).first()
        if document:
            document.processing_task_id = task_id
            document.parse_status = "pending"
            document.vector_status = "pending"
            document.error_message = None
        db.commit()
        return task_id
    finally:
        db.close()


def dispatch_pending_outbox(limit: int = 100) -> dict[str, int]:
    db = MySQLSessionLocal()
    try:
        ids = [
            int(row[0]) for row in db.query(TaskOutbox.id).filter(
                TaskOutbox.status == "pending"
            ).order_by(TaskOutbox.id.asc()).limit(limit).all()
        ]
    finally:
        db.close()
    dispatched = failed = 0
    for outbox_id in ids:
        try:
            dispatch_outbox_event(outbox_id)
            dispatched += 1
        except Exception:
            failed += 1
    return {"dispatched": dispatched, "failed": failed}
