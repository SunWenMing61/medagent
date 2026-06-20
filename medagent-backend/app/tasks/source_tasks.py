"""Tasks for online knowledge source synchronization.

Uses threading for Windows (where RQ's os.fork() is not available)
and falls back to RQ on Unix systems.
"""

import os
import sys
import threading

# Add project root to path for RQ worker
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.services.source_service import source_service


def sync_source(source_id: int, _job=None):
    """Synchronize an online knowledge source.

    Called by RQ on Unix or by direct thread on Windows.
    """
    return source_service.sync_source(source_id)


def enqueue_sync(source_id: int) -> None:
    """Enqueue a sync task. Uses threading on Windows for compatibility."""
    thread = threading.Thread(target=sync_source, args=(source_id,), daemon=True)
    thread.start()
