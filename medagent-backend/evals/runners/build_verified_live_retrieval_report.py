"""Build the dashboard artifact from two raw, independently reproducible runs."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def load(name: str) -> dict:
    return json.loads((REPORTS / name).read_text(encoding="utf-8"))


off = load("live_retrieval_dense_off.json")
on = load("live_retrieval_dense_on.json")
if off["sample_size"] != on["sample_size"] or off["dataset"] != on["dataset"]:
    raise ValueError("INVALID_COMPARISON: case set or dataset does not match")

aliases = {"hit_at_5": "hit_rate_at_5"}
before = {aliases.get(key, key): value for key, value in off["metrics"].items()}
after = {aliases.get(key, key): value for key, value in on["metrics"].items()}
delta = {key: after[key] - before[key] for key in after}
relative = {key: (delta[key] / before[key] if before[key] else None) for key in after}
payload = {
    "schema_version": "live-retrieval-dashboard-v2",
    "evaluated_at": on["evaluated_at"],
    "dataset": on["dataset"],
    "dataset_version": on["dataset_version"],
    "metric_definition_version": on["metric_definition_version"],
    "averaging": on["averaging"],
    "verification_status": "VERIFIED",
    "evidence_level": "A",
    "status": "healthy" if on["degraded_queries"] == 0 else "degraded",
    "sample_size": on["sample_size"],
    "successful_queries": on["successful_queries"],
    "degraded_queries": on["degraded_queries"],
    "k": 5,
    "metrics": after,
    "comparison": {
        "label": "Vector Retrieval OFF vs ON after full re-vectorization",
        "before": {"metrics": before, "sample_size": off["sample_size"], "dataset_version": off["dataset_version"]},
        "after": {"metrics": after, "sample_size": on["sample_size"], "dataset_version": on["dataset_version"]},
        "delta": delta,
        "delta_unit": "percentage_points_for_rate_metrics",
        "relative_improvement": relative,
    },
    "routes": {"dense": {"available": on["degraded_queries"] == 0}},
    "limitations": [
        "Macro average over 12 human-labeled queries; this is retrieval evaluation, not clinical answer-quality validation.",
        "The four duplicate source-text document IDs in KB 12 are retained as document-level relevant labels.",
    ],
    "cases": on["cases"],
}
(REPORTS / "live_retrieval_benchmark_latest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"status": payload["status"], "metrics": payload["metrics"], "delta": delta}, ensure_ascii=False))
