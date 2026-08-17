"""Deterministic regression evaluation with actionable failure attribution.

The evaluator intentionally does not call an LLM judge.  A versioned case file
defines the expected retrieval evidence, tool contract, answer facts and terminal
state.  Captured executions can therefore be compared across prompts, models and
retrieval strategies without judge-model drift.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


FAILURE_TYPES = (
    "retrieval_failure",
    "answer_hallucination",
    "tool_parameter_error",
    "task_incomplete",
)

_TOOL_INPUT_ERROR_CODES = {
    "TOOL_INPUT_INVALID",
    "INVALID_ARGUMENT",
    "VALIDATION_ERROR",
    "MISSING_ARGUMENT",
}
_CITATION_RE = re.compile(r"\[(ev_[A-Za-z0-9_-]+)\]")


class EvaluationDataError(ValueError):
    """Raised when the fixed dataset or a captured execution is malformed."""


@dataclass(frozen=True)
class EvaluationBundle:
    dataset_path: Path
    dataset_version: str
    dataset_sha256: str
    cases: list[dict[str, Any]]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EvaluationDataError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise EvaluationDataError(f"{path}:{line_number}: each JSONL row must be an object")
        rows.append(value)
    return rows


def load_fixed_dataset(path: str | Path) -> EvaluationBundle:
    dataset_path = Path(path).resolve()
    raw = dataset_path.read_bytes()
    cases = _read_jsonl(dataset_path)
    if not cases:
        raise EvaluationDataError("fixed dataset is empty")
    ids = [str(case.get("id", "")) for case in cases]
    if any(not case_id for case_id in ids):
        raise EvaluationDataError("every fixed case requires a non-empty id")
    duplicate_ids = sorted(case_id for case_id, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        raise EvaluationDataError(f"duplicate case ids: {', '.join(duplicate_ids)}")
    versions = {str(case.get("dataset_version", "")) for case in cases}
    if len(versions) != 1 or not next(iter(versions)):
        raise EvaluationDataError("all cases must share one non-empty dataset_version")
    for case in cases:
        if not str(case.get("query", "")).strip():
            raise EvaluationDataError(f"case {case['id']} requires a query")
        if case.get("requires_retrieval", True) and not (
            case.get("relevant_evidence_ids") or case.get("relevant_content_terms")
        ):
            raise EvaluationDataError(
                f"case {case['id']} requires retrieval labels (IDs or content terms)"
            )
    return EvaluationBundle(
        dataset_path=dataset_path,
        dataset_version=versions.pop(),
        dataset_sha256=hashlib.sha256(raw).hexdigest(),
        cases=cases,
    )


def load_captured_run(path: str | Path) -> list[dict[str, Any]]:
    rows = _read_jsonl(Path(path).resolve())
    ids = [str(row.get("case_id", "")) for row in rows]
    if any(not case_id for case_id in ids):
        raise EvaluationDataError("every captured execution requires case_id")
    duplicate_ids = sorted(case_id for case_id, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        raise EvaluationDataError(f"duplicate captured case ids: {', '.join(duplicate_ids)}")
    for row in rows:
        case_id = str(row["case_id"])
        if not isinstance(row.get("status"), str):
            raise EvaluationDataError(f"captured case {case_id} requires string status")
        if not isinstance(row.get("answer", row.get("final_answer")), str):
            raise EvaluationDataError(f"captured case {case_id} requires string answer")
        if not isinstance(row.get("retrieved_evidence"), list):
            raise EvaluationDataError(f"captured case {case_id} requires retrieved_evidence list")
        if not isinstance(row.get("tool_calls"), list):
            raise EvaluationDataError(f"captured case {case_id} requires tool_calls list")
        for evidence in row["retrieved_evidence"]:
            if not isinstance(evidence, dict) or not _evidence_id(evidence) or not isinstance(evidence.get("content"), str):
                raise EvaluationDataError(
                    f"captured case {case_id} has invalid evidence; evidence_id and content are required"
                )
        for call in row["tool_calls"]:
            if not isinstance(call, dict) or not isinstance(call.get("name"), str):
                raise EvaluationDataError(f"captured case {case_id} has invalid tool call name")
            if not isinstance(call.get("arguments"), dict) or not isinstance(call.get("status"), str):
                raise EvaluationDataError(
                    f"captured case {case_id} tool calls require object arguments and string status"
                )
    return rows


def _normal(text: Any) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _term_group_present(text: str, group: str | list[str]) -> bool:
    alternatives = [group] if isinstance(group, str) else group
    normalized = _normal(text)
    return any(_normal(item) in normalized for item in alternatives if str(item).strip())


def _evidence_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("evidence_id") or item.get("id") or "")
    return str(item)


def _retrieval_result(case: dict[str, Any], run: dict[str, Any]) -> tuple[bool, dict[str, float], list[str]]:
    if not case.get("requires_retrieval", True):
        return False, {
            "precision_at_k": 1.0, "recall_at_k": 1.0, "f1_at_k": 1.0,
            "hit_rate_at_k": 1.0, "mrr": 1.0, "ndcg_at_k": 1.0, "map_at_k": 1.0,
        }, []
    evidence = run.get("retrieved_evidence") or []
    top_k = int(case.get("evaluation_top_k", len(evidence) or 1))
    evidence = evidence[:top_k]
    expected_ids = {str(item) for item in case.get("relevant_evidence_ids", [])}
    ranked_ids = [_evidence_id(item) for item in evidence]
    retrieved_ids = set(ranked_ids)
    relevant_hits = sum(item in expected_ids for item in ranked_ids)
    precision = relevant_hits / len(ranked_ids) if ranked_ids else 0.0
    id_recall = len(expected_ids & retrieved_ids) / len(expected_ids) if expected_ids else 1.0

    corpus_text = " ".join(
        str(item.get("content", "")) if isinstance(item, dict) else "" for item in evidence
    )
    content_groups = case.get("relevant_content_terms", [])
    content_recall = (
        sum(_term_group_present(corpus_text, group) for group in content_groups) / len(content_groups)
        if content_groups else 1.0
    )
    # Standard retrieval recall is label-ID based when relevance IDs exist.
    # Content-term recall is the fallback for datasets that cannot provide stable IDs;
    # combining both with ``min`` would incorrectly penalize paraphrased evidence whose
    # explicitly labelled ID was already retrieved.
    recall = id_recall if expected_ids else content_recall
    hit_rate = 1.0 if recall > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    reciprocal_rank = 0.0
    for rank, evidence_id in enumerate(ranked_ids, 1):
        if evidence_id in expected_ids:
            reciprocal_rank = 1.0 / rank
            break
    if not expected_ids:
        reciprocal_rank = hit_rate
    if expected_ids:
        dcg = sum(
            1.0 / math.log2(rank + 1)
            for rank, evidence_id in enumerate(ranked_ids, 1)
            if evidence_id in expected_ids
        )
        ideal_count = min(len(expected_ids), top_k)
        ideal_dcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_count + 1))
        ndcg = dcg / ideal_dcg if ideal_dcg else 1.0
        hits_so_far = 0
        precision_sum = 0.0
        for rank, evidence_id in enumerate(ranked_ids, 1):
            if evidence_id in expected_ids:
                hits_so_far += 1
                precision_sum += hits_so_far / rank
        average_precision = precision_sum / ideal_count if ideal_count else 1.0
    else:
        ndcg = hit_rate
        average_precision = hit_rate
    threshold = float(case.get("min_retrieval_recall", 1.0))
    reasons: list[str] = []
    if id_recall < threshold:
        missing = sorted(expected_ids - retrieved_ids)
        reasons.append(f"relevant evidence missing from top-{top_k}: {missing}")
    if not expected_ids and content_recall < threshold:
        reasons.append(f"retrieved content term recall {content_recall:.3f} < {threshold:.3f}")
    return recall < threshold, {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "f1_at_k": f1,
        "hit_rate_at_k": hit_rate,
        "mrr": reciprocal_rank,
        "ndcg_at_k": ndcg,
        "map_at_k": average_precision,
    }, reasons


def _argument_rule_matches(arguments: dict[str, Any], key: str, rule: Any) -> bool:
    value = arguments.get(key)
    if not isinstance(rule, dict):
        return value == rule
    if "equals" in rule and value != rule["equals"]:
        return False
    if "one_of" in rule and value not in rule["one_of"]:
        return False
    if "min" in rule:
        try:
            if float(value) < float(rule["min"]):
                return False
        except (TypeError, ValueError):
            return False
    if "max" in rule:
        try:
            if float(value) > float(rule["max"]):
                return False
        except (TypeError, ValueError):
            return False
    if "contains" in rule:
        required = rule["contains"] if isinstance(rule["contains"], list) else [rule["contains"]]
        if isinstance(value, list):
            haystack = _normal(" ".join(str(item) for item in value))
        else:
            haystack = _normal(value)
        if not all(_normal(item) in haystack for item in required):
            return False
    return True


def _tool_result(case: dict[str, Any], run: dict[str, Any]) -> tuple[bool, float, list[str]]:
    calls = run.get("tool_calls") or []
    reasons: list[str] = []
    for call in calls:
        error_code = str(call.get("error_code") or "").upper()
        if error_code in _TOOL_INPUT_ERROR_CODES:
            reasons.append(f"{call.get('name', 'unknown')}: {error_code}")
    expected_calls = case.get("expected_tool_calls") or []
    passed = 0
    for expected in expected_calls:
        name = expected["name"]
        candidates = [call for call in calls if call.get("name") == name]
        if not candidates:
            reasons.append(f"required tool was not called: {name}")
            continue
        rules = expected.get("arguments", {})
        matching = [
            call for call in candidates
            if all(_argument_rule_matches(call.get("arguments") or {}, key, rule) for key, rule in rules.items())
            and str(call.get("status", "success")) not in {"error", "forbidden", "timeout", "cancelled"}
        ]
        if matching:
            passed += 1
        else:
            reasons.append(f"tool arguments/status did not satisfy contract: {name}")
    score = passed / len(expected_calls) if expected_calls else (0.0 if reasons else 1.0)
    return bool(reasons), score, reasons


def _hallucination_result(
    case: dict[str, Any], run: dict[str, Any], *, retrieval_failed: bool
) -> tuple[bool, float, list[str]]:
    answer = str(run.get("answer") or run.get("final_answer") or "")
    reasons: list[str] = []
    forbidden = case.get("forbidden_answer_terms") or []
    for term in forbidden:
        if _term_group_present(answer, term):
            reasons.append(f"forbidden/incorrect claim present: {term}")

    evidence_ids = {
        _evidence_id(item) for item in (run.get("retrieved_evidence") or [])
    }
    citations = {str(item) for item in (run.get("citations") or [])}
    citations.update(_CITATION_RE.findall(answer))
    invalid_citations = sorted(citation for citation in citations if citation not in evidence_ids)
    if invalid_citations:
        reasons.append(f"citations not present in retrieved evidence: {invalid_citations}")

    claims = run.get("claims") or run.get("structured_claims") or []
    if case.get("requires_citations", False) and answer.strip() and not retrieval_failed:
        if not citations and not claims:
            reasons.append("answer contains claims but no evidence citations")
        for claim in claims:
            claim_citations = claim.get("citation_ids") or claim.get("citations") or []
            if not claim_citations:
                reasons.append(f"uncited structured claim: {str(claim.get('claim', ''))[:80]}")
            elif any(str(item) not in evidence_ids for item in claim_citations):
                reasons.append(f"structured claim cites unavailable evidence: {claim_citations}")

    # Retrieval failure is attributed upstream rather than double-counted as hallucination,
    # unless the answer independently contains a known forbidden fact or fabricated citation.
    hallucinated = bool(reasons)
    return hallucinated, 0.0 if hallucinated else 1.0, reasons


def _completion_result(case: dict[str, Any], run: dict[str, Any]) -> tuple[bool, float, list[str]]:
    reasons: list[str] = []
    status = str(run.get("status") or "")
    allowed_statuses = {str(item) for item in case.get("allowed_terminal_statuses", ["completed"])}
    if status not in allowed_statuses:
        reasons.append(f"terminal status {status!r} not in {sorted(allowed_statuses)}")
    answer = str(run.get("answer") or run.get("final_answer") or "")
    if case.get("answer_required", True) and not answer.strip():
        reasons.append("final answer is empty")
    required_groups = case.get("required_answer_terms") or []
    missing_groups = [group for group in required_groups if not _term_group_present(answer, group)]
    if missing_groups:
        reasons.append(f"required answer facts missing: {missing_groups}")
    completed = not reasons
    if not required_groups:
        score = 1.0 if completed else 0.0
    else:
        fact_score = (len(required_groups) - len(missing_groups)) / len(required_groups)
        score = fact_score if status in allowed_statuses and answer.strip() else 0.0
    return not completed, score, reasons


def evaluate_case(case: dict[str, Any], run: dict[str, Any]) -> dict[str, Any]:
    retrieval_failed, retrieval_metrics, retrieval_reasons = _retrieval_result(case, run)
    tool_failed, tool_score, tool_reasons = _tool_result(case, run)
    hallucinated, grounding_score, hallucination_reasons = _hallucination_result(
        case, run, retrieval_failed=retrieval_failed
    )
    incomplete, completion_score, completion_reasons = _completion_result(case, run)
    flags = {
        "retrieval_failure": retrieval_failed,
        "answer_hallucination": hallucinated,
        "tool_parameter_error": tool_failed,
        "task_incomplete": incomplete,
    }
    primary_failure = "pass"
    for failure_type in ("tool_parameter_error", "retrieval_failure", "answer_hallucination", "task_incomplete"):
        if flags[failure_type]:
            primary_failure = failure_type
            break
    scores = {
        "retrieval": round(retrieval_metrics["recall_at_k"], 6),
        "grounded_answer": round(grounding_score, 6),
        "tool_arguments": round(tool_score, 6),
        "task_completion": round(completion_score, 6),
    }
    return {
        "case_id": case["id"],
        "requires_retrieval": bool(case.get("requires_retrieval", True)),
        "expects_tool_calls": bool(case.get("expected_tool_calls")),
        "passed": primary_failure == "pass",
        "primary_failure": primary_failure,
        "failure_flags": flags,
        "scores": scores,
        "retrieval_metrics": {
            name: round(value, 6) for name, value in retrieval_metrics.items()
        },
        "reasons": {
            "retrieval_failure": retrieval_reasons,
            "answer_hallucination": hallucination_reasons,
            "tool_parameter_error": tool_reasons,
            "task_incomplete": completion_reasons,
        },
    }


def evaluate_run(
    bundle: EvaluationBundle,
    captured_rows: Iterable[dict[str, Any]],
    *,
    run_id: str,
    configuration: dict[str, Any] | None = None,
) -> dict[str, Any]:
    captured = {str(row["case_id"]): row for row in captured_rows}
    unknown = sorted(set(captured) - {str(case["id"]) for case in bundle.cases})
    if unknown:
        raise EvaluationDataError(f"captured run contains unknown case ids: {', '.join(unknown)}")
    per_case: list[dict[str, Any]] = []
    for case in bundle.cases:
        row = captured.get(str(case["id"]))
        if row is None:
            row = {"case_id": case["id"], "status": "missing", "answer": ""}
        per_case.append(evaluate_case(case, row))

    count = len(per_case)
    retrieval_cases = [item for item in per_case if item["requires_retrieval"]]
    tool_cases = [item for item in per_case if item["expects_tool_calls"]]
    score_names = ("retrieval", "grounded_answer", "tool_arguments", "task_completion")
    component_populations = {
        "retrieval": retrieval_cases,
        "grounded_answer": per_case,
        "tool_arguments": tool_cases,
        "task_completion": per_case,
    }
    component_scores = {}
    for name in score_names:
        population = component_populations[name]
        component_scores[name] = round(
            sum(item["scores"][name] for item in population) / len(population)
            if population else 1.0,
            6,
        )
    weights = {"retrieval": 0.30, "grounded_answer": 0.30, "tool_arguments": 0.20, "task_completion": 0.20}
    overall = sum(component_scores[name] * weights[name] for name in score_names)
    failure_counts = {
        failure_type: sum(bool(item["failure_flags"][failure_type]) for item in per_case)
        for failure_type in FAILURE_TYPES
    }
    retrieval_summary = {
        name: round(
            sum(item["retrieval_metrics"][name] for item in retrieval_cases) / len(retrieval_cases)
            if retrieval_cases else 1.0,
            6,
        )
        for name in (
            "precision_at_k", "recall_at_k", "f1_at_k", "hit_rate_at_k",
            "mrr", "ndcg_at_k", "map_at_k",
        )
    }
    strict_pass_rate = round(sum(item["passed"] for item in per_case) / count, 6)
    return {
        "schema_version": "failure-regression-report-v2",
        "report_type": "deterministic_failure_regression",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "configuration": configuration or {},
        "dataset": {
            "version": bundle.dataset_version,
            "sha256": bundle.dataset_sha256,
            "case_count": count,
            "path": str(bundle.dataset_path),
        },
        "metrics": {
            "overall_score": round(overall, 6),
            "accuracy": strict_pass_rate,
            "strict_pass_rate": strict_pass_rate,
            "retrieval_metrics": retrieval_summary,
            "hallucination_free_rate": round(1.0 - failure_counts["answer_hallucination"] / count, 6),
            "tool_parameter_accuracy": component_scores["tool_arguments"],
            "task_completion_accuracy": round(1.0 - failure_counts["task_incomplete"] / count, 6),
            "component_scores": component_scores,
            "failure_counts": failure_counts,
            "failure_rates": {
                name: round(value / count, 6) for name, value in failure_counts.items()
            },
        },
        "per_case": per_case,
    }


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    baseline_dataset = baseline.get("dataset", {})
    candidate_dataset = candidate.get("dataset", {})
    if baseline_dataset.get("sha256") != candidate_dataset.get("sha256"):
        raise EvaluationDataError("baseline and candidate must use the exact same dataset SHA-256")
    baseline_cases = {item["case_id"]: item for item in baseline.get("per_case", [])}
    candidate_cases = {item["case_id"]: item for item in candidate.get("per_case", [])}
    if set(baseline_cases) != set(candidate_cases):
        raise EvaluationDataError("baseline and candidate case sets differ")

    metric_deltas: dict[str, float] = {}
    for name, value in baseline["metrics"]["component_scores"].items():
        metric_deltas[name] = round(candidate["metrics"]["component_scores"][name] - value, 6)
    metric_deltas["overall_score"] = round(
        candidate["metrics"]["overall_score"] - baseline["metrics"]["overall_score"], 6
    )
    metric_deltas["strict_pass_rate"] = round(
        candidate["metrics"]["strict_pass_rate"] - baseline["metrics"]["strict_pass_rate"], 6
    )
    failure_rate_deltas = {
        name: round(
            candidate["metrics"]["failure_rates"][name]
            - baseline["metrics"]["failure_rates"][name], 6
        )
        for name in FAILURE_TYPES
    }
    retrieval_metric_deltas = {
        name: round(
            candidate["metrics"]["retrieval_metrics"].get(name, 0.0)
            - value,
            6,
        )
        for name, value in baseline["metrics"].get("retrieval_metrics", {}).items()
    }
    regressions = [
        case_id for case_id in sorted(baseline_cases)
        if baseline_cases[case_id]["passed"] and not candidate_cases[case_id]["passed"]
    ]
    fixes = [
        case_id for case_id in sorted(baseline_cases)
        if not baseline_cases[case_id]["passed"] and candidate_cases[case_id]["passed"]
    ]
    overall_delta = metric_deltas["overall_score"]
    worsened_failure_types = [name for name, delta in failure_rate_deltas.items() if delta > 0]
    if overall_delta > 0 and not regressions and not worsened_failure_types:
        verdict = "better"
    elif overall_delta < 0 or (regressions and not fixes):
        verdict = "worse"
    elif overall_delta == 0 and not regressions and not fixes and not worsened_failure_types:
        verdict = "unchanged"
    else:
        verdict = "mixed"
    return {
        "schema_version": "failure-regression-comparison-v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": baseline_dataset,
        "baseline_run_id": baseline.get("run_id"),
        "candidate_run_id": candidate.get("run_id"),
        "verdict": verdict,
        "regression": verdict in {"worse", "mixed"} and bool(regressions or worsened_failure_types or overall_delta < 0),
        "metric_deltas": metric_deltas,
        "retrieval_metric_deltas": retrieval_metric_deltas,
        "failure_rate_deltas": failure_rate_deltas,
        "regressed_cases": regressions,
        "fixed_cases": fixes,
        "worsened_failure_types": worsened_failure_types,
    }


def read_report(path: str | Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise EvaluationDataError("report must be a JSON object")
    return value
