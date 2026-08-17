"""Configurable release hard gate and baseline/candidate comparison."""

from __future__ import annotations

from typing import Any


DEFAULT_GATE = {"min_task_completion": 0.80, "min_answer_quality": 0.75, "min_rag_quality": 0.70, "min_tool_accuracy": 0.80, "min_faithfulness": 0.75, "min_execution_mode_accuracy": 0.90, "max_under_routing_rate": 0.03, "max_over_routing_rate": 0.10, "max_unnecessary_multi_agent_rate": 0.10, "max_token_regression": 0.10, "max_cost_regression": 0.10, "max_regression_drop": 0.02, "max_p95_latency_ms": 8000, "max_critical_failures": 0, "max_critical_routing_failures": 0}


class ReleaseGate:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = {**DEFAULT_GATE, **(config or {})}

    def evaluate(self, metrics: dict[str, float], *, critical_failures: int = 0, regression_drop: float = 0.0) -> dict[str, Any]:
        checks = [
            ("task_completion", metrics.get("task_completion", 0), ">=", self.config["min_task_completion"]),
            ("answer_quality", metrics.get("answer_quality", 0), ">=", self.config["min_answer_quality"]),
            ("rag", metrics.get("rag", 0), ">=", self.config["min_rag_quality"]),
            ("tool", metrics.get("tool", 0), ">=", self.config["min_tool_accuracy"]),
            ("faithfulness", metrics.get("faithfulness", metrics.get("answer_quality", 0)), ">=", self.config["min_faithfulness"]),
            ("execution_mode_accuracy", metrics.get("execution_mode_accuracy", 0), ">=", self.config["min_execution_mode_accuracy"]),
            ("under_routing_rate", metrics.get("under_routing_rate", 0), "<=", self.config["max_under_routing_rate"]),
            ("over_routing_rate", metrics.get("over_routing_rate", 0), "<=", self.config["max_over_routing_rate"]),
            ("unnecessary_multi_agent_rate", metrics.get("unnecessary_multi_agent_rate", 0), "<=", self.config["max_unnecessary_multi_agent_rate"]),
            ("p95_latency_ms", metrics.get("p95_latency_ms", 0), "<=", self.config["max_p95_latency_ms"]),
            ("regression_drop", regression_drop, "<=", self.config["max_regression_drop"]),
            ("critical_failures", critical_failures, "<=", self.config["max_critical_failures"]),
        ]
        reasons = [f"{name}: {actual:.4g} {operator} {threshold:.4g} failed" for name, actual, operator, threshold in checks if not (actual >= threshold if operator == ">=" else actual <= threshold)]
        return {"status": "fail" if reasons else "pass", "passed": not reasons, "reasons": reasons, "config": self.config, "critical_safety_failure": critical_failures > 0}


def compare_case_results(baseline: list[dict], candidate: list[dict]) -> dict[str, Any]:
    old, new = ({x["case_key"]: x for x in rows} for rows in (baseline, candidate))
    rows = []
    counts = {"improved": 0, "regressed": 0, "fixed": 0, "new_failure": 0, "unchanged": 0, "critical_regressions": 0}
    for case_key in sorted(set(old) & set(new)):
        before, after = old[case_key], new[case_key]
        delta = round(float(after["overall_score"]) - float(before["overall_score"]), 6)
        if not before["passed"] and after["passed"]: classification = "fixed"
        elif before["passed"] and not after["passed"]: classification = "new_failure"
        elif delta < -0.000001: classification = "regressed"
        elif delta > 0.000001: classification = "improved"
        else: classification = "unchanged"
        counts[classification] += 1
        critical = bool(after.get("critical") and not before.get("critical"))
        counts["critical_regressions"] += int(critical)
        rows.append({"case_key": case_key, "category": after.get("category"), "baseline_score": before["overall_score"], "candidate_score": after["overall_score"], "delta": delta, "classification": classification, "critical": critical, "reason": after.get("failure_reason")})
    return {"summary": counts, "cases": rows}
