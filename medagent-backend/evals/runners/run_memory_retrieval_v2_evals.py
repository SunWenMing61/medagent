"""Executed deterministic benchmark for Memory/Retrieval v2 (non-clinical)."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _rrf(routes, k=60):
    scores = {}
    for route in routes:
        for rank, item_id in enumerate(route, 1):
            scores[item_id] = scores.get(item_id, 0.0) + 1 / (k + rank)
    return scores


def _retrieval(case, upgraded: bool):
    candidates = case["candidates"]
    if not upgraded:
        return [row[0] for row in sorted(candidates, key=lambda row: -(0.7 * row[2] + 0.3 * row[3]))]
    dense = [row[0] for row in sorted(candidates, key=lambda row: -row[2])]
    sparse = [row[0] for row in sorted(candidates, key=lambda row: -row[3])]
    exact_rows = []
    exact_score = {}
    for row in candidates:
        count = sum(term.casefold() in row[1].casefold() for term in case["terms"])
        if count:
            exact_score[row[0]] = count / len(case["terms"])
            exact_rows.append(row[0])
    exact_rows.sort(key=lambda item: -exact_score[item])
    rrf = _rrf([dense, sparse, exact_rows])
    return sorted(dense, key=lambda item: (-exact_score.get(item, 0), -rrf[item], item))


def _memory(case, upgraded: bool):
    candidates = case["candidates"]
    if not upgraded:
        return [row[0] for row in candidates if any(token in row[4] for token in case["query"].split())]
    return [row[0] for row in candidates if row[1] == case["tenant"] and row[2] == case["user"] and row[3] == "user"]


def _metrics(rankings, relevant):
    reciprocal = []
    hits = []
    for ranked, target in zip(rankings, relevant):
        rank = ranked.index(target) + 1 if target in ranked else 0
        reciprocal.append(1 / rank if rank else 0)
        hits.append(1 if rank == 1 else 0)
    return {"mrr": sum(reciprocal) / len(reciprocal), "hit_rate_at_1": sum(hits) / len(hits)}


def main():
    data = json.loads((ROOT / "datasets" / "memory_retrieval_v2_cases.json").read_text(encoding="utf-8"))
    targets = [case["relevant"] for case in data["retrieval"]]
    baseline_rank = [_retrieval(case, False) for case in data["retrieval"]]
    upgraded_rank = [_retrieval(case, True) for case in data["retrieval"]]
    baseline_retrieval = _metrics(baseline_rank, targets)
    upgraded_retrieval = _metrics(upgraded_rank, targets)

    memory_targets = [case["relevant"] for case in data["memory"]]
    baseline_memory_rank = [_memory(case, False) for case in data["memory"]]
    upgraded_memory_rank = [_memory(case, True) for case in data["memory"]]
    baseline_memory = _metrics(baseline_memory_rank, memory_targets)
    upgraded_memory = _metrics(upgraded_memory_rank, memory_targets)
    leakage_baseline = sum(any(item.startswith("leak") or item.startswith("assistant") for item in rows) for rows in baseline_memory_rank) / len(data["memory"])
    leakage_upgraded = sum(any(item.startswith("leak") or item.startswith("assistant") for item in rows) for rows in upgraded_memory_rank) / len(data["memory"])

    report = {
        "benchmark": "memory_retrieval_v2_deterministic_offline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "clinical_validity": False,
        "live_model_or_provider_used": False,
        "dataset": {"retrieval_cases": len(data["retrieval"]), "memory_cases": len(data["memory"])},
        "baseline": {"retrieval": baseline_retrieval, "memory": baseline_memory, "memory_leakage_case_rate": leakage_baseline},
        "upgraded": {"retrieval": upgraded_retrieval, "memory": upgraded_memory, "memory_leakage_case_rate": leakage_upgraded},
        "absolute_improvement": {
            "retrieval_mrr": upgraded_retrieval["mrr"] - baseline_retrieval["mrr"],
            "retrieval_hit_rate_at_1": upgraded_retrieval["hit_rate_at_1"] - baseline_retrieval["hit_rate_at_1"],
            "memory_mrr": upgraded_memory["mrr"] - baseline_memory["mrr"],
            "memory_leakage_case_rate_reduction": leakage_baseline - leakage_upgraded,
        },
        "method": "Baseline weighted Dense/Sparse ranking versus Exact+Dense+Sparse RRF; flat unscoped Memory versus tenant/user/source-role filtering.",
    }
    output = ROOT / "reports" / "memory_retrieval_v2_latest.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
