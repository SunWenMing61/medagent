"""Reproducible, zero-network routing benchmark for the Hybrid Runtime."""

from __future__ import annotations

import json
from pathlib import Path

from app.hybrid.complexity_router import ComplexityRouter
from app.hybrid.runtime_monitor import RuntimeComplexityMonitor


ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evals" / "datasets" / "hybrid_routing_cases.jsonl"
REPORT = ROOT / "evals" / "reports" / "hybrid_routing_benchmark_latest.json"


def main() -> None:
    router = ComplexityRouter()
    rows = [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]
    results = []
    for row in rows:
        decision = router.route(row["query"])
        results.append({
            "id": row["id"], "expected": row["expected_execution_mode"],
            "actual": decision.execution_mode.value, "score": decision.score,
            "confidence": decision.confidence, "passed": decision.execution_mode.value == row["expected_execution_mode"],
        })
    monitor = RuntimeComplexityMonitor()
    escalation_case = {"react_step_count": 4, "tool_call_count": 3, "tool_call_names": ["patient_data", "local_knowledge_base", "calculator"], "sub_questions": [{}, {}, {}], "completed_tasks": [], "tokens_used": 2200}
    reason = monitor.escalation_reason(escalation_case)
    expected_modes = [item["expected"] for item in results]
    actual_modes = [item["actual"] for item in results]
    ordering = {"DIRECT": 0, "REACT": 1, "MULTI_AGENT": 2}
    report = {
        "dataset": str(DATASET.relative_to(ROOT)),
        "sample_size": len(results),
        "execution_mode_accuracy": sum(item["passed"] for item in results) / len(results),
        "under_routing_rate": sum(ordering.get(actual, 0) < ordering.get(expected, 0) for expected, actual in zip(expected_modes, actual_modes)) / len(results),
        "over_routing_rate": sum(ordering.get(actual, 0) > ordering.get(expected, 0) for expected, actual in zip(expected_modes, actual_modes)) / len(results),
        "unnecessary_multi_agent_rate": sum(actual == "MULTI_AGENT" and expected != "MULTI_AGENT" for expected, actual in zip(expected_modes, actual_modes)) / len(results),
        "router_tokens": 0,
        "escalation_validation": {"expected": "MULTI_AGENT", "actual": "MULTI_AGENT" if reason else "REACT", "reason": reason, "passed": bool(reason)},
        "cases": results,
        "limitations": [
            "This benchmark measures deterministic routing and escalation decisions, not answer-generation quality.",
            "Token/cost/latency savings require matched production traces or an executed all-multi-agent baseline and are not fabricated here.",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
