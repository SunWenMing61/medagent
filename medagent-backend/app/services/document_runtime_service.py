"""API-side maintenance for durable document ingestion and vectorization."""

from __future__ import annotations

import logging
import threading

from app.core.config import settings
from app.services.outbox_service import dispatch_pending_outbox
from app.tasks.document_tasks import recover_pending_vectorization

logger = logging.getLogger(__name__)


class DocumentRuntimeService:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="document-auto-vectorization-runtime",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)
        self._thread = None

    def _run(self) -> None:
        interval = max(int(settings.OUTBOX_DISPATCH_INTERVAL_SECONDS), 1)
        while not self._stop_event.is_set():
            try:
                outbox = dispatch_pending_outbox(limit=1000)
                recovery = (
                    recover_pending_vectorization(limit=1000)
                    if settings.DOCUMENT_AUTO_RECOVERY_ENABLED
                    else {"scheduled": 0, "failed": 0}
                )
                if outbox["dispatched"] or outbox["failed"] or recovery["scheduled"] or recovery["failed"]:
                    logger.info(
                        "Document runtime maintenance: outbox=%s vectorization_recovery=%s",
                        outbox,
                        recovery,
                    )
            except Exception:
                logger.exception("Document runtime maintenance failed")
            self._stop_event.wait(interval)


document_runtime_service = DocumentRuntimeService()
