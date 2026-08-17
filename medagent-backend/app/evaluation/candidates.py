"""Privacy-safe candidate mining, semantic deduplication and human review helpers."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select

from app.evaluation.trace import redact
from app.models.evaluation import EvaluationCandidate


_SYNONYMS = {"不良反应": "副作用", "不良事件": "副作用", " adverse effect ": " 副作用 ", " side effect ": " 副作用 ", "用药量": "剂量"}


def normalize_query(text: str) -> str:
    value = str(redact(text)).lower().strip()
    for source, target in _SYNONYMS.items():
        value = value.replace(source, target)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\u4e00-\u9fff]+", " ", value)).strip()


def _vector(text: str, size: int = 128) -> list[float]:
    normalized = normalize_query(text)
    units = normalized.split() + [normalized[i:i + 2] for i in range(max(0, len(normalized) - 1))]
    values = [0.0] * size
    for unit, count in Counter(units).items():
        values[int(hashlib.sha256(unit.encode()).hexdigest()[:8], 16) % size] += float(count)
    norm = math.sqrt(sum(item * item for item in values)) or 1.0
    return [item / norm for item in values]


def semantic_similarity(left: str, right: str) -> float:
    a, b = _vector(left), _vector(right)
    return sum(x * y for x, y in zip(a, b))


class CandidateService:
    weights = {"failure": .30, "business_value": .15, "novelty": .15, "difficulty": .10, "safety": .15, "cost": .15}

    def score(self, *, failure: float, business_value: float, novelty: float, difficulty: float, safety: float, cost: float) -> tuple[float, dict]:
        values = {name: max(0.0, min(1.0, float(value))) for name, value in locals().items() if name != "self"}
        return round(sum(values[name] * weight for name, weight in self.weights.items()), 4), values

    def create(self, db, *, query: str, source_request_id: str | None = None, metadata: dict | None = None) -> EvaluationCandidate:
        normalized = normalize_query(query)
        digest = hashlib.sha256(normalized.encode()).hexdigest()
        exact = db.scalar(select(EvaluationCandidate).where(EvaluationCandidate.normalized_hash == digest))
        if exact:
            return exact
        rows = db.scalars(select(EvaluationCandidate).where(EvaluationCandidate.status != "rejected").limit(500)).all()
        nearest = max(rows, key=lambda item: semantic_similarity(normalized, item.query_text), default=None)
        similarity = semantic_similarity(normalized, nearest.query_text) if nearest else 0.0
        if nearest and similarity >= .92:
            return nearest
        details = metadata or {}
        score, breakdown = self.score(
            failure=details.get("failure", 1 if details.get("status") in {"failed", "error"} else .4),
            business_value=details.get("business_value", .5), novelty=1 - similarity,
            difficulty=details.get("difficulty_score", .5), safety=details.get("safety_score", .3),
            cost=details.get("cost_score", min(1, details.get("total_tokens", 0) / 6000)),
        )
        row = EvaluationCandidate(
            id=uuid.uuid4().hex, normalized_hash=digest, query_text=normalized,
            source_request_id=source_request_id, cluster_key=nearest.cluster_key if nearest and similarity >= .72 else digest[:16],
            category=details.get("category", "production_failure"), difficulty=details.get("difficulty", "medium"),
            score=score, score_breakdown=breakdown, runtime_metadata=redact(details),
        )
        db.add(row); db.flush()
        return row

    @staticmethod
    def review(row: EvaluationCandidate, *, decision: str, reviewer_id: int, comment: str | None = None) -> None:
        if row.status not in {"pending", "approved"}:
            raise ValueError("Candidate is no longer reviewable")
        row.status = decision
        row.reviewed_by = reviewer_id
        row.review_comment = comment
        row.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)


candidate_service = CandidateService()
