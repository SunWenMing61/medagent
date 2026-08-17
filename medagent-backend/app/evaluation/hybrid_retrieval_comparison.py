"""Fixed medical retrieval benchmark for dense-only and production-style hybrid search.

The corpus is synthetic and contains no patient data.  It is designed to detect
retrieval regressions across medical settings; it is not a clinical validation
benchmark and must not be presented as one.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.services.retrieval_service import reciprocal_rank_fusion


BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = BACKEND_ROOT / "evals" / "datasets" / "medical_retrieval_benchmark_v3.json"
DEFAULT_K_VALUES = (1, 3, 5)


def _dense_ranking(case: dict[str, Any]) -> list[str]:
    return [row[0] for row in sorted(case["candidates"], key=lambda row: (-float(row[2]), row[0]))]


def _hybrid_ranking(case: dict[str, Any]) -> list[str]:
    candidates = case["candidates"]
    id_map = {str(row[0]): index + 1 for index, row in enumerate(candidates)}
    reverse = {value: key for key, value in id_map.items()}

    dense = [
        {"id": id_map[str(row[0])], "document_id": id_map[str(row[0])], "content": row[1], "dense_score": float(row[2])}
        for row in sorted(candidates, key=lambda row: (-float(row[2]), str(row[0])))
    ]
    sparse = [
        {"id": id_map[str(row[0])], "document_id": id_map[str(row[0])], "content": row[1], "sparse_score": float(row[3])}
        for row in sorted(candidates, key=lambda row: (-float(row[3]), str(row[0])))
    ]
    exact = []
    exact_scores: dict[int, float] = {}
    terms = [str(term) for term in case.get("terms", []) if str(term).strip()]
    for row in candidates:
        content = str(row[1]).casefold()
        hits = sum(term.casefold() in content for term in terms)
        if hits:
            score = hits / max(len(terms), 1)
            candidate_id = id_map[str(row[0])]
            exact_scores[candidate_id] = score
            exact.append({
                "id": candidate_id,
                "document_id": candidate_id,
                "content": row[1],
                "exact_score": score,
            })
    exact.sort(key=lambda item: (-float(item["exact_score"]), int(item["id"])))
    fused = reciprocal_rank_fusion([dense, sparse, exact])
    fused.sort(key=lambda item: (
        -float(exact_scores.get(int(item["id"]), 0.0)),
        -float(item.get("rrf_score") or 0.0),
        int(item["id"]),
    ))
    return [reverse[int(item["id"])] for item in fused]


def _relevance(case: dict[str, Any]) -> dict[str, float]:
    labelled = case.get("relevance")
    if isinstance(labelled, dict) and labelled:
        return {str(key): max(float(value), 0.0) for key, value in labelled.items() if float(value) > 0}
    relevant = case.get("relevant", [])
    if isinstance(relevant, str):
        relevant = [relevant]
    return {str(item): 1.0 for item in relevant}


def _dcg(grades: Iterable[float]) -> float:
    return sum((2.0 ** grade - 1.0) / math.log2(rank + 1) for rank, grade in enumerate(grades, 1))


def _average_precision_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    hits = 0
    precision_sum = 0.0
    for rank, item in enumerate(ranked[:k], 1):
        if item in relevant:
            hits += 1
            precision_sum += hits / rank
    return precision_sum / min(len(relevant), k)


def _metrics(
    rankings: list[list[str]],
    cases: list[dict[str, Any]],
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
) -> dict[str, float]:
    if not rankings:
        return {}
    samples: dict[str, list[float]] = defaultdict(list)
    for ranked, case in zip(rankings, cases):
        grades = _relevance(case)
        relevant = set(grades)
        first_rank = next((rank for rank, item in enumerate(ranked, 1) if item in relevant), 0)
        samples["mrr"].append(1.0 / first_rank if first_rank else 0.0)
        for k in k_values:
            top = ranked[:k]
            hits = sum(item in relevant for item in top)
            precision = hits / k if k > 0 else 0.0
            recall = hits / len(relevant) if relevant else 0.0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
            samples[f"precision_at_{k}"].append(precision)
            samples[f"recall_at_{k}"].append(recall)
            samples[f"f1_at_{k}"].append(f1)
            samples[f"hit_rate_at_{k}"].append(float(hits > 0))
            samples[f"map_at_{k}"].append(_average_precision_at_k(ranked, relevant, k))
            actual_grades = [grades.get(item, 0.0) for item in top]
            ideal_grades = sorted(grades.values(), reverse=True)[:k]
            ideal = _dcg(ideal_grades)
            samples[f"ndcg_at_{k}"].append(_dcg(actual_grades) / ideal if ideal else 0.0)

    metrics = {name: sum(values) / len(values) for name, values in samples.items()}
    # Top-1 relevance accuracy is retained for compatibility with the existing UI/API.
    metrics["accuracy_at_1"] = metrics.get("hit_rate_at_1", 0.0)
    return {name: round(value, 6) for name, value in metrics.items()}


def _category_metrics(
    rankings: list[list[str]], cases: list[dict[str, Any]]
) -> dict[str, dict[str, float]]:
    grouped_cases: dict[str, list[dict[str, Any]]] = defaultdict(list)
    grouped_rankings: dict[str, list[list[str]]] = defaultdict(list)
    for ranking, case in zip(rankings, cases):
        category = str(case.get("category") or "other")
        grouped_cases[category].append(case)
        grouped_rankings[category].append(ranking)
    return {
        category: _metrics(grouped_rankings[category], grouped_cases[category])
        for category in sorted(grouped_cases)
    }


def run_hybrid_retrieval_comparison(dataset_path: str | Path = DEFAULT_DATASET) -> dict[str, Any]:
    path = Path(dataset_path)
    raw = path.read_bytes()
    data = json.loads(raw)
    cases = data["retrieval"]
    baseline_rankings = [_dense_ranking(case) for case in cases]
    hybrid_rankings = [_hybrid_ranking(case) for case in cases]
    baseline = _metrics(baseline_rankings, cases)
    hybrid = _metrics(hybrid_rankings, cases)
    absolute = {name: round(hybrid[name] - baseline[name], 6) for name in baseline}
    relative = {
        name: round((hybrid[name] - baseline[name]) / baseline[name], 6) if baseline[name] else None
        for name in baseline
    }
    categories = sorted({str(case.get("category") or "other") for case in cases})
    return {
        "schema_version": "medical-retrieval-benchmark-v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": str(path),
            "version": str(data.get("version") or "unknown"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "case_count": len(cases),
            "category_count": len(categories),
            "categories": categories,
            "clinical_validity": False,
            "contains_patient_data": False,
            "description": data.get("description"),
        },
        "baseline": {
            "strategy": "dense_only",
            "metrics": baseline,
            "by_category": _category_metrics(baseline_rankings, cases),
        },
        "candidate": {
            "strategy": "dense_sparse_exact_rrf",
            "metrics": hybrid,
            "by_category": _category_metrics(hybrid_rankings, cases),
        },
        "improvement": {"absolute": absolute, "relative": relative},
        "per_case": [
            {
                "case_id": str(case.get("id") or index + 1),
                "category": str(case.get("category") or "other"),
                "query": case["query"],
                "relevant": list(_relevance(case)),
                "baseline_first_relevant_rank": next(
                    (rank for rank, item in enumerate(baseline_rankings[index], 1) if item in _relevance(case)), 0
                ),
                "hybrid_first_relevant_rank": next(
                    (rank for rank, item in enumerate(hybrid_rankings[index], 1) if item in _relevance(case)), 0
                ),
            }
            for index, case in enumerate(cases)
        ],
    }
