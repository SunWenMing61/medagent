"""Server-issued evidence IDs and strict citation validation."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass

from app.core.config import settings

_CITATION_PATTERN = re.compile(r"\[(ev_[a-f0-9]{16})\]")


@dataclass(slots=True)
class CitationValidation:
    answer: str
    references: list[dict]
    invalid_ids: list[str]


def issue_evidence_ids(evidence: list[dict]) -> list[dict]:
    issued = []
    secret = settings.SECRET_KEY.encode("utf-8")
    for item in evidence:
        payload = f"{item['kb_id']}:{item['document_id']}:{item['id']}".encode("utf-8")
        evidence_id = "ev_" + hmac.new(secret, payload, hashlib.sha256).hexdigest()[:16]
        enriched = dict(item)
        enriched["evidence_id"] = evidence_id
        issued.append(enriched)
    return issued


def validate_citations(answer: str, references: list[dict]) -> CitationValidation:
    allowed = {str(reference.get("evidence_id")): reference for reference in references}
    cited = []
    invalid = []
    seen = set()
    for evidence_id in _CITATION_PATTERN.findall(answer or ""):
        if evidence_id in allowed:
            if evidence_id not in seen:
                cited.append(allowed[evidence_id])
                seen.add(evidence_id)
        else:
            invalid.append(evidence_id)
    sanitized = answer
    for evidence_id in set(invalid):
        sanitized = sanitized.replace(f"[{evidence_id}]", "[无效引用已移除]")
    return CitationValidation(sanitized, cited, sorted(set(invalid)))
