"""Privacy-minimized retrieval traces for debugging and aggregate monitoring."""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from typing import Any

from app.db.session import MySQLSessionLocal
from app.models.memory import RetrievalTrace


_SENSITIVE = re.compile(
    r"\b1[3-9]\d{9}\b|\b\d{15,18}[0-9Xx]\b|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"(?:姓名|患者|身份证|手机号)[:：]?\s*[\u4e00-\u9fffA-Za-z0-9*_-]{2,24}"
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_text(value: str, limit: int = 500) -> str:
    return _SENSITIVE.sub("[REDACTED]", value or "")[:limit]


def _json_safe(value: Any, *, include_content: bool = False) -> Any:
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"content", "context_content"}:
                if include_content:
                    result["content_preview"] = _safe_text(str(item), 240)
                result["content_hash"] = _hash(str(item))
            elif key in {"embedding", "query_vector"}:
                continue
            else:
                result[str(key)] = _json_safe(item, include_content=include_content)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, include_content=include_content) for item in value[:100]]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class RetrievalObservabilityService:
    def record(self, **payload) -> None:
        db = MySQLSessionLocal()
        try:
            request_id = str(payload["request_id"])
            row = db.query(RetrievalTrace).filter(RetrievalTrace.request_id == request_id).first()
            values = {
                "tenant_id": int(payload["tenant_id"]),
                "user_id": int(payload["user_id"]),
                "original_query_hash": _hash(str(payload.get("original_query") or "")),
                "standalone_query": _safe_text(str(payload.get("standalone_query") or ""), 1000),
                "routes_json": _json_safe(payload.get("routes") or []),
                "entities_json": _json_safe(payload.get("entities") or []),
                "constraints_json": _json_safe(payload.get("constraints") or []),
                "rankings_json": _json_safe(payload.get("rankings") or {}),
                "filtered_json": _json_safe(payload.get("filtered") or []),
                "final_evidence_json": _json_safe(payload.get("final_evidence") or [], include_content=True),
                "timings_json": _json_safe(payload.get("timings") or {}),
                "status": str(payload.get("status") or "error")[:32],
                "error_json": _json_safe(payload.get("error")) if payload.get("error") else None,
            }
            if row is None:
                row = RetrievalTrace(request_id=request_id, **values)
                db.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


retrieval_observability_service = RetrievalObservabilityService()
