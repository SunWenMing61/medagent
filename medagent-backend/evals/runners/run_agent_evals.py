"""Run deterministic, offline Agent-level evaluations against versioned JSONL cases."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.answer_generator_agent import answer_generator_agent
from app.agents.clarification_agent import clarification_agent
from app.agents.evidence_verifier_agent import evidence_verifier_agent
from app.agents.input_triage_agent import input_triage_agent
from app.agents.output_safety_agent import output_safety_agent
from app.agents.retrieval_planner_agent import retrieval_planner_agent
from app.agents.schemas import RetrievalPlan, StructuredAnswer
from app.graphs.graph_state import new_agent_state
from app.graphs.root_graph import build_controlled_workflow


ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "datasets"


def _load(name: str) -> list[dict]:
    path = DATASETS / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _ratio(values: list[bool]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_triage() -> dict:
    rows = []
    for case in _load("triage_cases.jsonl"):
        result = input_triage_agent.run(case["query"])
        rows.append({
            "id": case["id"],
            "intent_correct": result.intent == case["expected_intent"],
            "risk_correct": result.risk_level == case["expected_risk"],
            "emergency_truth": case["expected_emergency"],
            "emergency_prediction": result.need_emergency_response,
            "clarification_correct": result.need_clarification == case["expected_clarification"],
        })
    emergency_truth = [row for row in rows if row["emergency_truth"]]
    emergency_predictions = [row for row in rows if row["emergency_prediction"]]
    true_emergencies = [row for row in rows if row["emergency_truth"] and row["emergency_prediction"]]
    high_risk = [row for row, case in zip(rows, _load("triage_cases.jsonl")) if case["expected_risk"] in {"high", "emergency"}]
    return {
        "dataset_size": len(rows),
        "intent_accuracy": _ratio([row["intent_correct"] for row in rows]),
        "risk_accuracy": _ratio([row["risk_correct"] for row in rows]),
        "emergency_recall": len(true_emergencies) / len(emergency_truth) if emergency_truth else 1.0,
        "emergency_precision": len(true_emergencies) / len(emergency_predictions) if emergency_predictions else 1.0,
        "high_risk_recall": _ratio([row["risk_correct"] for row in high_risk]),
        "clarification_accuracy": _ratio([row["clarification_correct"] for row in rows]),
        "per_case": rows,
    }


def evaluate_clarification() -> dict:
    rows = []
    for case in _load("clarification_cases.jsonl"):
        triage = input_triage_agent.run(case["query"])
        result = clarification_agent.run(triage)
        count = len(result.questions)
        rows.append({
            "id": case["id"],
            "correct": result.need_clarification == case["expected_need_clarification"]
            and case["min_questions"] <= count <= case["max_questions"],
            "question_count": count,
        })
    return {"dataset_size": len(rows), "accuracy": _ratio([row["correct"] for row in rows]), "per_case": rows}


def evaluate_planning() -> dict:
    rows = []
    for case in _load("retrieval_planning_cases.jsonl"):
        triage = input_triage_agent.run(case["query"])
        plan = retrieval_planner_agent.run(case["query"], triage)
        preserved = all(term in plan.original_query for term in case["preserve_terms"])
        rows.append({
            "id": case["id"],
            "route_correct": plan.retrieval_routes == case["expected_routes"],
            "term_preservation_correct": preserved,
        })
    return {
        "dataset_size": len(rows),
        "route_accuracy": _ratio([row["route_correct"] for row in rows]),
        "term_preservation_rate": _ratio([row["term_preservation_correct"] for row in rows]),
        "per_case": rows,
    }


def evaluate_evidence() -> dict:
    rows = []
    for case in _load("evidence_verification_cases.jsonl"):
        plan = RetrievalPlan(
            original_query=case["query"], normalized_query=case["query"],
            local_queries=[case["query"]], retrieval_routes=["local_knowledge_base"], reason="eval",
        )
        result = evidence_verifier_agent.run(plan, case["evidence"])
        rows.append({
            "id": case["id"],
            "status_correct": result.evidence_status == case["expected_status"],
            "rejection_correct": set(result.rejected_evidence_ids) == set(case["expected_rejected"]),
        })
    return {
        "dataset_size": len(rows),
        "sufficiency_accuracy": _ratio([row["status_correct"] for row in rows]),
        "unsupported_rejection_accuracy": _ratio([row["rejection_correct"] for row in rows]),
        "per_case": rows,
    }


def evaluate_answer() -> dict:
    rows = []
    for case in _load("answer_generation_cases.jsonl"):
        result = answer_generator_agent.run(case["query"], case["evidence"])
        cited = [citation for detail in result.details for citation in detail.citation_ids]
        rows.append({
            "id": case["id"],
            "citation_correct": set(cited) == set(case["expected_citation_ids"]),
            "all_claims_cited": all(detail.citation_ids for detail in result.details),
        })
    return {
        "dataset_size": len(rows),
        "citation_correctness": _ratio([row["citation_correct"] for row in rows]),
        "citation_completeness": _ratio([row["all_claims_cited"] for row in rows]),
        "per_case": rows,
    }


def evaluate_safety() -> dict:
    rows = []
    for case in _load("safety_cases.jsonl"):
        result = output_safety_agent.run(
            StructuredAnswer.model_validate(case["answer"]),
            allowed_evidence_ids=set(case["allowed_evidence_ids"]),
            risk_level=case["risk_level"],
        )
        rows.append({"id": case["id"], "correct": result.safety_status == case["expected_status"]})
    return {"dataset_size": len(rows), "status_accuracy": _ratio([row["correct"] for row in rows]), "per_case": rows}


def evaluate_end_to_end() -> dict:
    rows = []
    for case in _load("end_to_end_cases.jsonl"):
        state = new_agent_state(raw_query=case["query"], user_id=1, tenant_id=1, authorized_kb_ids=[])
        result = build_controlled_workflow(persist=False, trace=False).run(state)
        rows.append({
            "id": case["id"],
            "correct": result["status"] == case["expected_status"]
            and result["risk_level"] == case["expected_risk"]
            and result["agent_call_count"] <= case["expected_max_agent_calls"]
            and result["tool_call_count"] <= case["expected_max_tool_calls"],
            "status": result["status"],
            "agent_calls": result["agent_call_count"],
            "tool_calls": result["tool_call_count"],
        })
    return {
        "dataset_size": len(rows),
        "task_success_rate": _ratio([row["correct"] for row in rows]),
        "average_agent_calls": sum(row["agent_calls"] for row in rows) / len(rows),
        "average_tool_calls": sum(row["tool_calls"] for row in rows) / len(rows),
        "per_case": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "report_type": "executed_offline_example_dataset",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_notice": "Synthetic regression examples; not a clinical benchmark and not a live-provider result.",
        "results": {
            "triage": evaluate_triage(),
            "clarification": evaluate_clarification(),
            "retrieval_planning": evaluate_planning(),
            "evidence_verification": evaluate_evidence(),
            "answer_generation": evaluate_answer(),
            "safety": evaluate_safety(),
            "end_to_end": evaluate_end_to_end(),
        },
    }
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
