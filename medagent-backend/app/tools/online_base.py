"""Shared helpers for normalized online medical evidence."""

import hashlib
import hmac

from app.core.config import settings


def online_evidence_id(source: str, stable_identifier: str) -> str:
    payload = f"{source}:{stable_identifier}".encode("utf-8")
    digest = hmac.new(settings.SECRET_KEY.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return "ev_" + digest[:16]
