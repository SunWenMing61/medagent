from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.failure_taxonomy import (
    EvaluationDataError,
    compare_reports,
    evaluate_case,
    evaluate_run,
    load_captured_run,
    load_fixed_dataset,
)


DATASET = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "failure_taxonomy_v1.jsonl"


def _case() -> dict:
    return {
        "id": "case-1",
        "query": "测试问题",
        "requires_retrieval": True,
        "relevant_evidence_ids": ["ev_good"],
        "relevant_content_terms": ["正确事实"],
        "min_retrieval_recall": 1.0,
        "expected_tool_calls": [{
            "name": "local_knowledge_base",
            "arguments": {"query": {"contains": ["测试"]}, "top_k": {"min": 1, "max": 50}},
        }],
        "required_answer_terms": ["正确事实"],
        "forbidden_answer_terms": ["错误事实"],
        "requires_citations": True,
        "allowed_terminal_statuses": ["completed"],
    }


def _passing_run() -> dict:
    return {
        "case_id": "case-1",
        "status": "completed",
        "answer": "正确事实 [ev_good]",
        "retrieved_evidence": [{"evidence_id": "ev_good", "content": "正确事实"}],
        "citations": ["ev_good"],
        "claims": [{"claim": "正确事实", "citation_ids": ["ev_good"]}],
        "tool_calls": [{
            "name": "local_knowledge_base",
            "arguments": {"query": "测试问题", "top_k": 10},
            "status": "success",
        }],
    }


def test_fixed_dataset_is_versioned_and_fingerprinted():
    bundle = load_fixed_dataset(DATASET)
    assert bundle.dataset_version == "failure-taxonomy-v1"
    assert len(bundle.cases) == 12
    assert len(bundle.dataset_sha256) == 64
    assert all(case.get("frozen_evidence") is not None for case in bundle.cases)


def test_passing_execution_has_no_failure():
    result = evaluate_case(_case(), _passing_run())
    assert result["passed"] is True
    assert result["primary_failure"] == "pass"
    assert not any(result["failure_flags"].values())
    assert result["retrieval_metrics"] == {
        "precision_at_k": 1.0,
        "recall_at_k": 1.0,
        "f1_at_k": 1.0,
        "hit_rate_at_k": 1.0,
        "mrr": 1.0,
        "ndcg_at_k": 1.0,
        "map_at_k": 1.0,
    }


def test_retrieval_precision_and_recall_are_reported_separately():
    run = _passing_run()
    run["retrieved_evidence"].append({"evidence_id": "ev_noise", "content": "无关内容"})
    result = evaluate_case(_case(), run)
    assert result["retrieval_metrics"]["precision_at_k"] == 0.5
    assert result["retrieval_metrics"]["recall_at_k"] == 1.0
    assert result["retrieval_metrics"]["hit_rate_at_k"] == 1.0
    assert result["retrieval_metrics"]["mrr"] == 1.0
    assert result["retrieval_metrics"]["ndcg_at_k"] == 1.0
    assert result["retrieval_metrics"]["map_at_k"] == 1.0


def test_labelled_evidence_id_controls_recall_even_when_wording_is_paraphrased():
    case = _case()
    case["relevant_content_terms"] = ["必须逐字出现但实际没有"]
    result = evaluate_case(case, _passing_run())
    assert result["failure_flags"]["retrieval_failure"] is False
    assert result["retrieval_metrics"]["recall_at_k"] == 1.0


def test_tool_parameter_error_is_distinguished():
    run = _passing_run()
    run["tool_calls"][0]["arguments"]["top_k"] = 500
    result = evaluate_case(_case(), run)
    assert result["primary_failure"] == "tool_parameter_error"
    assert result["failure_flags"]["tool_parameter_error"] is True
    assert result["failure_flags"]["retrieval_failure"] is False


def test_tool_validation_error_is_distinguished():
    run = _passing_run()
    run["tool_calls"][0].update(status="error", error_code="TOOL_INPUT_INVALID")
    result = evaluate_case(_case(), run)
    assert result["primary_failure"] == "tool_parameter_error"
    assert any("TOOL_INPUT_INVALID" in reason for reason in result["reasons"]["tool_parameter_error"])


def test_retrieval_failure_is_distinguished_from_hallucination():
    run = _passing_run()
    run["retrieved_evidence"] = [{"evidence_id": "ev_wrong", "content": "无关内容"}]
    run["citations"] = []
    run["claims"] = []
    run["answer"] = "正确事实"
    result = evaluate_case(_case(), run)
    assert result["primary_failure"] == "retrieval_failure"
    assert result["failure_flags"]["retrieval_failure"] is True


def test_answer_hallucination_is_distinguished():
    run = _passing_run()
    run["answer"] = "错误事实 [ev_good]"
    result = evaluate_case(_case(), run)
    assert result["primary_failure"] == "answer_hallucination"
    assert result["failure_flags"]["retrieval_failure"] is False
    assert result["failure_flags"]["answer_hallucination"] is True


def test_task_incomplete_is_distinguished():
    run = _passing_run()
    run["answer"] = "已查询，但没有给出结论 [ev_good]"
    result = evaluate_case(_case(), run)
    assert result["primary_failure"] == "task_incomplete"
    assert result["failure_flags"]["answer_hallucination"] is False
    assert result["failure_flags"]["task_incomplete"] is True


def test_missing_captured_case_becomes_task_failure(tmp_path: Path):
    dataset = tmp_path / "cases.jsonl"
    case = _case() | {"dataset_version": "test-v1"}
    dataset.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    report = evaluate_run(load_fixed_dataset(dataset), [], run_id="missing")
    assert report["metrics"]["strict_pass_rate"] == 0.0
    assert report["per_case"][0]["failure_flags"]["task_incomplete"] is True


def test_report_exposes_named_accuracy_and_retrieval_metrics(tmp_path: Path):
    dataset = tmp_path / "cases.jsonl"
    case = _case() | {"dataset_version": "test-v1"}
    dataset.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    report = evaluate_run(load_fixed_dataset(dataset), [_passing_run()], run_id="named-metrics")
    assert report["metrics"]["accuracy"] == 1.0
    assert report["metrics"]["retrieval_metrics"]["precision_at_k"] == 1.0
    assert report["metrics"]["retrieval_metrics"]["recall_at_k"] == 1.0
    assert report["metrics"]["tool_parameter_accuracy"] == 1.0
    assert report["metrics"]["task_completion_accuracy"] == 1.0


def test_comparison_reports_improvement_and_regression(tmp_path: Path):
    dataset = tmp_path / "cases.jsonl"
    case = _case() | {"dataset_version": "test-v1"}
    dataset.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    bundle = load_fixed_dataset(dataset)
    bad_run = _passing_run()
    bad_run["answer"] = "错误事实 [ev_good]"
    baseline = evaluate_run(bundle, [bad_run], run_id="baseline")
    candidate = evaluate_run(bundle, [_passing_run()], run_id="candidate")
    improved = compare_reports(baseline, candidate)
    assert improved["verdict"] == "better"
    assert improved["fixed_cases"] == ["case-1"]
    regressed = compare_reports(candidate, baseline)
    assert regressed["verdict"] == "worse"
    assert regressed["regression"] is True
    assert regressed["regressed_cases"] == ["case-1"]


def test_comparison_rejects_different_datasets():
    baseline = {"dataset": {"sha256": "a"}, "per_case": [], "metrics": {}}
    candidate = {"dataset": {"sha256": "b"}, "per_case": [], "metrics": {}}
    with pytest.raises(EvaluationDataError, match="same dataset"):
        compare_reports(baseline, candidate)


def test_captured_run_contract_rejects_missing_runtime_fields(tmp_path: Path):
    captured = tmp_path / "captured.jsonl"
    captured.write_text('{"case_id":"case-1","status":"completed"}\n', encoding="utf-8")
    with pytest.raises(EvaluationDataError, match="answer"):
        load_captured_run(captured)
