import asyncio

from app.evaluation.contracts import CaseExecution
from app.evaluation.evaluators import RAGEvaluator, ToolEvaluator, retrieval_metrics


def test_empty_relevance_is_not_a_perfect_retrieval_score():
    metrics = retrieval_metrics(["a"], [], k=5)
    assert metrics == {
        "hit_rate_at_k": 0.0,
        "precision_at_k": 0.0,
        "recall_at_k": 0.0,
        "mrr": 0.0,
        "ndcg_at_k": 0.0,
    }


def test_rag_without_ground_truth_is_not_applicable():
    result = asyncio.run(RAGEvaluator().evaluate(
        {"category": "rag", "expected": {}, "thresholds": {}},
        CaseExecution(output="answer", retrievals=[{"document_id": "a"}]),
    ))[0]
    assert result.score == 0.0
    assert result.details["not_applicable"] is True


def test_tool_metrics_separate_exact_precision_recall_and_arguments():
    case = {"expected": {"tools": ["a", "b"], "tool_args": {"a": {"x": 1}}}, "thresholds": {}}
    trace = CaseExecution(output="ok", tool_calls=[
        {"tool_name": "a", "arguments": {"x": 1}, "success": True},
        {"tool_name": "x", "arguments": {}, "success": True},
    ])
    result = asyncio.run(ToolEvaluator().evaluate(case, trace))[0]
    assert result.details["selection_exact_match"] == 0.0
    assert result.details["tool_precision"] == 0.5
    assert result.details["tool_recall"] == 0.5
    assert result.details["argument_accuracy"] == 1.0


def test_redundant_tool_call_requires_same_tool_and_same_arguments():
    case = {"expected": {"tools": ["a"]}, "thresholds": {}}
    trace = CaseExecution(output="ok", tool_calls=[
        {"tool_name": "a", "arguments": {"page": 1}, "success": True},
        {"tool_name": "a", "arguments": {"page": 2}, "success": True},
        {"tool_name": "a", "arguments": {"page": 2}, "success": True},
    ])
    result = asyncio.run(ToolEvaluator().evaluate(case, trace))[0]
    assert result.details["redundant_tool_call_rate"] == 1 / 3
