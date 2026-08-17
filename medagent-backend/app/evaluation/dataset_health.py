"""Versioning, drift and health analytics for living benchmark datasets."""

from __future__ import annotations

import math
import uuid
from collections import Counter

from sqlalchemy import select

from app.evaluation.candidates import semantic_similarity
from app.models.evaluation import DatasetChangeLog, EvalCase, EvalCaseResult, EvalDataset, EvalDatasetVersion, EvalRun


def _distribution(rows, field: str) -> dict[str, float]:
    counts = Counter(str(getattr(row, field, "unknown")) for row in rows)
    total = sum(counts.values()) or 1
    return {key: value / total for key, value in counts.items()}


def js_divergence(left: dict[str, float], right: dict[str, float]) -> float:
    keys = set(left) | set(right)
    midpoint = {key: (left.get(key, 0) + right.get(key, 0)) / 2 for key in keys}
    def kl(source):
        return sum(value * math.log2(value / midpoint[key]) for key, value in source.items() if value > 0 and midpoint[key] > 0)
    return round((kl(left) + kl(right)) / 2, 6)


class DatasetHealthService:
    @staticmethod
    def create_version(db, dataset: EvalDataset, *, actor_id: int | None, summary: str) -> EvalDatasetVersion:
        cases = db.scalars(select(EvalCase).where(EvalCase.dataset_id == dataset.id).order_by(EvalCase.case_key)).all()
        version = EvalDatasetVersion(
            id=uuid.uuid4().hex, dataset_id=dataset.id, version=dataset.version, case_count=len(cases),
            change_summary=summary, created_by=actor_id,
            snapshot_json=[{"case_key": row.case_key, "category": row.category, "difficulty": row.difficulty, "tags": row.tags} for row in cases],
        )
        db.add(version)
        return version

    def calculate(self, db, dataset_id: str) -> dict:
        dataset = db.get(EvalDataset, dataset_id)
        if not dataset:
            raise LookupError(dataset_id)
        cases = list(db.scalars(select(EvalCase).where(EvalCase.dataset_id == dataset_id)).all())
        duplicate_pairs = 0
        for index, left in enumerate(cases):
            duplicate_pairs += sum(1 for right in cases[index + 1:] if semantic_similarity(left.input_text, right.input_text) >= .92)
        category = _distribution(cases, "category")
        difficulty = _distribution(cases, "difficulty")
        latest_versions = list(db.scalars(select(EvalDatasetVersion).where(EvalDatasetVersion.dataset_id == dataset_id).order_by(EvalDatasetVersion.created_at.desc()).limit(2)).all())
        drift = 0.0
        if len(latest_versions) == 2:
            old = Counter(row.get("category", "unknown") for row in latest_versions[1].snapshot_json)
            total = sum(old.values()) or 1
            drift = js_divergence({key: value / total for key, value in old.items()}, category)
        run_ids = db.scalars(select(EvalRun.id).where(EvalRun.dataset_id == dataset_id, EvalRun.status == "completed").order_by(EvalRun.created_at.desc()).limit(10)).all()
        results = list(db.scalars(select(EvalCaseResult).where(EvalCaseResult.run_id.in_(run_ids))).all()) if run_ids else []
        by_case: dict[str, list[float]] = {}
        for row in results: by_case.setdefault(row.case_key, []).append(row.overall_score)
        comparable = [values for values in by_case.values() if len(values) > 1]
        discriminatory = sum(max(values) - min(values) for values in comparable) / len(comparable) if comparable else None
        required_categories = {"basic_qa", "agent_routing", "rag", "tool_calling", "safety", "multi_agent"}
        coverage = len(required_categories & set(category)) / len(required_categories)
        health_score = max(0.0, min(1.0, .45 * coverage + .30 * (1 - min(1, duplicate_pairs / max(1, len(cases)))) + .25 * (1 - drift)))
        verified_ground_truth = sum((row.source_json or {}).get("verification_status") in {"reviewed", "expert_verified"} for row in cases)
        return {"dataset_id": dataset.id, "version": dataset.version, "case_count": len(cases), "health_score": round(health_score, 4), "health_score_definition":"0.45 category coverage + 0.30 uniqueness + 0.25 category JS stability", "coverage": round(coverage, 4), "category_distribution": category, "difficulty_distribution": difficulty, "duplicate_pairs": duplicate_pairs, "duplicate_rate": round(duplicate_pairs / max(1, len(cases)), 4), "duplicate_definition":{"type":"semantic_proxy","algorithm":"sha256-hashed character-bigram cosine","threshold":0.92}, "drift_js": drift if len(latest_versions) == 2 else None, "drift_method":"Jensen-Shannon divergence over category distribution", "discriminative_power": round(discriminatory, 4) if discriminatory is not None else None, "discriminative_power_status":"VERIFIED" if discriminatory is not None else "UNTESTED", "authoritative_ground_truth_rate": round(verified_ground_truth / len(cases), 4) if cases else None, "ground_truth_status":"VERIFIED" if verified_ground_truth else "UNTESTED"}

    @staticmethod
    def log_change(db, *, dataset_id: str, version: str, action: str, case_key: str, candidate_id: str | None, actor_id: int | None, details: dict) -> None:
        db.add(DatasetChangeLog(dataset_id=dataset_id, version=version, action=action, case_key=case_key, candidate_id=candidate_id, actor_id=actor_id, details_json=details))


dataset_health_service = DatasetHealthService()
