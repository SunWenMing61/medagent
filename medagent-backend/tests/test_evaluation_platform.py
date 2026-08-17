import asyncio
import json

from app.evaluation.contracts import CaseExecution
from app.evaluation.dataset_loader import DatasetLoader
from app.evaluation.evaluators import (
    AnswerQualityEvaluator, FunctionalEvaluator, RAGEvaluator, RoutingEvaluator, SafetyEvaluator,
    ToolEvaluator, TrajectoryEvaluator, compare_arguments, retrieval_metrics,
)
from app.evaluation.release_gate import ReleaseGate, compare_case_results
from app.evaluation.trace import redact, trace_scope
from app.evaluation.judge import LLMJudge, JudgeOutput


def test_dataset_loader_supports_json_and_jsonl(tmp_path):
    rows = [{"id": "a", "input": "x"}, {"id": "b", "input": "y"}]
    json_file = tmp_path / "data.json"
    json_file.write_text(json.dumps({"cases": rows}), encoding="utf-8")
    jsonl_file = tmp_path / "data.jsonl"
    jsonl_file.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    loader = DatasetLoader()
    assert loader.load(json_file) == rows
    assert loader.load(jsonl_file) == rows
    loader.validate(rows[0])


def test_nested_argument_comparison_supports_subset_lists_tolerance_and_ignore():
    expected = {"patient": {"id": "P1", "age": 40}, "values": [1.0, 2], "timestamp": "ignore"}
    actual = {"patient": {"id": "P1", "age": 40, "name": "redacted"}, "values": [2, 1.005], "timestamp": "different", "extra": True}
    assert compare_arguments(expected, actual, ignore_fields={"timestamp"}, float_tolerance=.01)
    assert not compare_arguments(expected, actual, mode="exact", ignore_fields={"timestamp"}, float_tolerance=.01)


def test_retrieval_metrics_are_standard_rank_metrics():
    metrics = retrieval_metrics(["x", "b", "a"], ["a", "b"], k=3)
    assert metrics["hit_rate_at_k"] == 1
    assert metrics["precision_at_k"] == 2 / 3
    assert metrics["recall_at_k"] == 1
    assert metrics["mrr"] == .5
    assert 0 < metrics["ndcg_at_k"] <= 1


def test_answer_quality_without_labels_is_not_applicable():
    case = {"category": "basic_qa", "expected": {"facts": [], "required_content": []}, "thresholds": {}}
    result = asyncio.run(AnswerQualityEvaluator().evaluate(case, CaseExecution(output="grounded answer")))[0]
    assert result.score == 0
    assert result.details["not_applicable"] is True


def test_retrieval_metrics_deduplicate_repeated_document_chunks():
    metrics = retrieval_metrics(["doc1", "doc1", "doc2"], ["doc1", "doc2"], k=5)
    assert metrics["precision_at_k"] == 2 / 5
    assert metrics["recall_at_k"] == 1
    assert metrics["ndcg_at_k"] == 1


def test_answer_quality_marks_component_outputs_not_applicable():
    case = {"category": "tool_calling", "expected": {}, "thresholds": {}}
    result = asyncio.run(AnswerQualityEvaluator().evaluate(case, CaseExecution(output="tool-a")))[0]
    assert result.passed and result.details["not_applicable"] is True


def test_all_deterministic_evaluators_and_safety_hard_failure():
    case = {"expected": {"required_content": ["fact"], "documents": ["doc1"], "tools": ["lookup"], "tool_args": {"lookup": {"id": 1}}, "agents": ["supervisor", "retrieval"], "trajectory": ["plan", "lookup"]}, "thresholds": {}, "is_critical": True}
    trace = CaseExecution(output="fact", agent_steps=[{"action": "plan"}, {"action": "lookup"}], routing_history=["supervisor", "retrieval"], retrievals=[{"document_id": "doc1"}], tool_calls=[{"tool_name": "lookup", "arguments": {"id": 1}, "success": True}], metadata={"safety_violations": ["unsafe_medical_instruction"]})
    evaluators = [FunctionalEvaluator(), RAGEvaluator(), ToolEvaluator(), RoutingEvaluator(), TrajectoryEvaluator(), SafetyEvaluator()]
    results = [asyncio.run(evaluator.evaluate(case, trace))[0] for evaluator in evaluators]
    assert all(item.score == 1 for item in results[:-1])
    assert results[-1].passed is False
    assert results[-1].details["critical_safety_failure"] is True


def test_release_gate_fails_critical_safety_even_with_perfect_score():
    metrics = {"task_completion": 1, "answer_quality": 1, "rag": 1, "tool": 1, "faithfulness": 1, "p95_latency_ms": 100}
    gate = ReleaseGate().evaluate(metrics, critical_failures=1)
    assert gate["status"] == "fail"
    assert gate["critical_safety_failure"] is True


def test_regression_comparison_matches_by_case_key_not_order():
    baseline = [{"case_key": "a", "overall_score": .9, "passed": True}, {"case_key": "b", "overall_score": .4, "passed": False}]
    candidate = [{"case_key": "b", "overall_score": .8, "passed": True}, {"case_key": "a", "overall_score": .7, "passed": True}]
    result = compare_case_results(baseline, candidate)
    assert result["summary"]["regressed"] == 1
    assert result["summary"]["fixed"] == 1


def test_trace_context_isolated_and_redacts_identifiers():
    with trace_scope() as first:
        first.step("agent", "act", input_data="email patient@example.com phone 13800138000")
    with trace_scope() as second:
        assert second.steps == []
    assert "patient@example.com" not in str(first.steps)
    assert "13800138000" not in str(first.steps)
    assert redact({"api_key": "secret", "safe": "ok"}) == {"safe": "ok"}


def test_llm_judge_requires_structured_output():
    class Client:
        async def parse(self, *, model, prompt, response_model):
            assert model == "judge-model"
            assert "judge_prompt_version=judge-v2" in prompt
            assert response_model is JudgeOutput
            return JudgeOutput(score=.9, passed=True, reason="grounded", evidence=["doc1"])
    result = asyncio.run(LLMJudge(Client(), model="judge-model", prompt_version="judge-v2").evaluate(rubric="faithfulness", case={"id":"c"}, output="answer", evidence=[]))
    assert result.score == .9 and result.passed
