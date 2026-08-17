"""Load the latest auditable live-retrieval benchmark report."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPORT_PATH = Path(__file__).resolve().parents[2] / "evals" / "reports" / "live_retrieval_benchmark_latest.json"


def load_live_retrieval_report() -> dict[str, Any]:
    """Return the checked-in benchmark artifact used by the dashboard."""
    if not REPORT_PATH.exists():
        return {"status": "missing", "sample_size": 0, "successful_queries": 0, "degraded_queries": 0, "metrics": {}}
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))
