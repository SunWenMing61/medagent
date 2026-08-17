"""Import the repository's versioned real deterministic regression cases."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.evaluation.dataset_loader import dataset_loader
from app.models.evaluation import EvalCase, EvalDataset


BACKEND = Path(__file__).resolve().parents[2]
FILES = {
    "hybrid_routing_cases.jsonl": "hybrid_routing",
    "triage_cases.jsonl": "agent_routing",
    "retrieval_planning_cases.jsonl": "rag",
    "tool_selection_cases.jsonl": "tool_calling",
    "answer_generation_cases.jsonl": "basic_qa",
    "complex_answer_cases.jsonl": "complex_qa",
    "safety_cases.jsonl": "safety",
    "end_to_end_cases.jsonl": "multi_agent",
}


def ensure_default_dataset(db) -> EvalDataset:
    dataset_id = "medagent-regression-v1"
    dataset = db.get(EvalDataset, dataset_id)
    if not dataset:
        dataset = EvalDataset(id=dataset_id, name="MedAgent Repository Regression Suite", version="2.0.0", description="Versioned repository cases including complex evidence-synthesis questions. Synthetic evaluation data; no patient data.", source="jsonl", case_count=0)
        db.add(dataset); db.flush()
    else:
        dataset.version = "2.0.0"
        dataset.description = "Versioned repository cases including complex evidence-synthesis questions. Synthetic evaluation data; no patient data."
    existing = {row.case_key: row for row in db.scalars(select(EvalCase).where(EvalCase.dataset_id == dataset_id)).all()}
    count = 0
    for filename, category in FILES.items():
        for raw in dataset_loader.load(BACKEND / "evals" / "datasets" / filename):
            dataset_loader.validate(raw)
            expected = {
                "facts": raw.get("expected_facts", []), "documents": raw.get("expected_documents", []),
                "agents": raw.get("expected_agents", []), "tools": raw.get("expected_tools", raw.get("expected", []) if category == "tool_calling" else []),
                "tool_args": raw.get("expected_tool_args", {}), "trajectory": raw.get("expected_trajectory", []),
                "required_content": raw.get("required_content", []), "forbidden_content": raw.get("forbidden_content", []),
                "answer_quality_applicable": raw.get("answer_quality_applicable", category in {"basic_qa", "complex_qa"}),
            }
            if category == "hybrid_routing":
                expected["execution_mode"] = raw.get("expected_execution_mode")
                expected["complexity"] = raw.get("expected_complexity")
            if category == "rag": expected["documents"] = raw.get("expected_routes", [])
            if category == "agent_routing": expected["agents"] = ["input_triage"] + ([] if raw.get("expected_emergency") else ["retrieval_planner"])
            if category == "complex_qa":
                expected["execution_mode"] = "MULTI_AGENT"
                expected["agents"] = ["input_triage", "retrieval_planner", "evidence_verifier", "answer_generator_detailed"]
                expected["trajectory"] = ["triage", "plan_retrieval", "verify_evidence", "generate_answer"]
                expected["documents"] = raw.get("expected_citation_ids", [])
            values = dict(name=raw.get("name", raw["id"]), category=category, difficulty=raw.get("difficulty", "medium"), tags=raw.get("tags", [category]), is_critical=bool(raw.get("is_critical", category == "safety" and raw.get("expected_status") != "pass")), input_text=str(raw.get("query") or raw.get("input") or raw.get("answer") or raw.get("intent") or raw["id"]), expected_json=expected, thresholds_json=raw.get("thresholds", {}), source_json=raw)
            row = existing.get(raw["id"])
            if row:
                for key, value in values.items(): setattr(row, key, value)
            else:
                db.add(EvalCase(dataset_id=dataset_id, case_key=raw["id"], **values))
            count += 1
    dataset.case_count = count
    db.commit()
    return dataset
