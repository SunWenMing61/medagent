"""Authenticated Evaluation Platform API consumed by the administration UI."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import require_admin
from app.db.session import get_mysql_db
from app.evaluation.release_gate import ReleaseGate, compare_case_results
from app.evaluation.candidates import candidate_service
from app.evaluation.dataset_health import dataset_health_service
from app.evaluation.live_retrieval import load_live_retrieval_report
from app.evaluation.runner import evaluation_runner
from app.evaluation.seed import ensure_default_dataset
from app.models.evaluation import EvalCase, EvalCaseResult, EvalDataset, EvalDatasetVersion, EvalMetricResult, EvalRun, EvaluationCandidate, EvaluationTrace
from app.models.user import User

router = APIRouter()


class RunCreate(BaseModel):
    name: str | None = None
    dataset_id: str | None = None
    mode: Literal["FAST", "FULL", "CUSTOM"] = "FAST"
    agent_version: str = "current"
    model: str | None = None
    categories: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    max_cases: int | None = Field(default=None, ge=1, le=5000)
    concurrency: int = Field(default=2, ge=1, le=8)
    timeout: float = Field(default=45, ge=1, le=600)
    retry: int = Field(default=1, ge=0, le=3)
    seed: int = 0
    release_gate: dict = Field(default_factory=dict)
    architecture: Literal["HYBRID", "SIMPLE_RAG", "ALL_MULTI_AGENT"] = "HYBRID"


class CandidateCreate(BaseModel):
    query: str = Field(min_length=2, max_length=4000)
    source_request_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class CandidateReview(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class CandidateAdd(BaseModel):
    dataset_id: str
    name: str = Field(min_length=2, max_length=255)
    expected: dict
    verification_status: Literal["reviewed", "expert_verified"]
    category: str = "production_regression"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    tags: list[str] = Field(default_factory=list)
    is_critical: bool = False


def _run(row: EvalRun, dataset_name: str | None = None) -> dict:
    return {"id": row.id, "name": row.name, "dataset_id": row.dataset_id, "dataset_name": dataset_name, "status": row.status, "mode": row.mode, "architecture": (row.config_json or {}).get("architecture", "HYBRID"), "is_baseline": (row.config_json or {}).get("architecture") == "SIMPLE_RAG", "agent_version": row.agent_version, "model_name": row.model_name, "model_version": row.model_version, "prompt_version": row.prompt_version, "embedding_model": row.embedding_model, "embedding_version": row.embedding_version, "git_commit": row.git_commit, "judge_model": row.judge_model, "judge_prompt_version": row.judge_prompt_version, "random_seed": row.random_seed, "started_at": row.started_at, "finished_at": row.finished_at, "duration_ms": row.duration_ms, "total_cases": row.total_cases, "completed_cases": row.completed_cases, "passed_cases": row.passed_cases, "failed_cases": row.failed_cases, "critical_failures": row.critical_failures, "overall_score": row.overall_score, "pass_rate": row.passed_cases / row.total_cases if row.total_cases else 0, "release_gate_status": row.release_gate_status, "release_gate": row.release_gate_json or {}, "error": row.error, "created_at": row.created_at}


def _metrics(db: Session, run_id: str) -> dict[str, float]:
    return {row.metric_name: row.score for row in db.scalars(select(EvalMetricResult).where(EvalMetricResult.run_id == run_id)).all()}


def _case(db: Session, row: EvalCaseResult) -> dict:
    case = db.get(EvalCase, row.case_id)
    return {"id": row.id, "run_id": row.run_id, "case_id": case.case_key, "case_key": row.case_key, "name": case.name, "category": case.category, "difficulty": case.difficulty, "tags": case.tags, "is_critical": case.is_critical, "input": case.input_text, "expected": case.expected_json, "thresholds": case.thresholds_json, "trace_id": row.trace_id, "status": row.status, "passed": row.passed, "critical": row.critical, "overall_score": row.overall_score, "scores": row.scores_json, "actual_output": row.actual_output, "failure_reason": row.failure_reason, "judge_reason": row.judge_reason, "details": row.details_json, "latency_ms": row.latency_ms, "input_tokens": row.input_tokens, "output_tokens": row.output_tokens, "estimated_cost": row.estimated_cost}


@router.get("/datasets")
def datasets(_admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    ensure_default_dataset(db)
    return [{"id": row.id, "name": row.name, "version": row.version, "description": row.description, "case_count": row.case_count} for row in db.scalars(select(EvalDataset).order_by(EvalDataset.name)).all()]


@router.get("/datasets/{dataset_id}")
def dataset_detail(dataset_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    dataset = db.get(EvalDataset, dataset_id)
    if not dataset: raise HTTPException(404, "Evaluation dataset not found")
    cases = db.scalars(select(EvalCase).where(EvalCase.dataset_id == dataset_id).order_by(EvalCase.case_key)).all()
    return {"id": dataset.id, "name": dataset.name, "version": dataset.version, "description": dataset.description, "case_count": dataset.case_count, "cases": [{"id": row.id, "case_key": row.case_key, "name": row.name, "category": row.category, "difficulty": row.difficulty, "tags": row.tags, "is_critical": row.is_critical} for row in cases]}


@router.get("/datasets/{dataset_id}/versions")
def dataset_versions(dataset_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    if not db.get(EvalDataset, dataset_id): raise HTTPException(404, "Evaluation dataset not found")
    rows = db.scalars(select(EvalDatasetVersion).where(EvalDatasetVersion.dataset_id == dataset_id).order_by(EvalDatasetVersion.created_at.desc())).all()
    return [{"id": row.id, "version": row.version, "case_count": row.case_count, "change_summary": row.change_summary, "created_by": row.created_by, "created_at": row.created_at} for row in rows]


@router.get("/datasets/{dataset_id}/health")
def dataset_health(dataset_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    try: return dataset_health_service.calculate(db, dataset_id)
    except LookupError: raise HTTPException(404, "Evaluation dataset not found")


def _candidate(row: EvaluationCandidate) -> dict:
    return {"id": row.id, "query_text": row.query_text, "source_request_id": row.source_request_id, "cluster_key": row.cluster_key, "category": row.category, "difficulty": row.difficulty, "status": row.status, "score": row.score, "score_breakdown": row.score_breakdown, "runtime_metadata": row.runtime_metadata, "review_comment": row.review_comment, "reviewed_by": row.reviewed_by, "reviewed_at": row.reviewed_at, "target_dataset_id": row.target_dataset_id, "target_case_id": row.target_case_id, "created_at": row.created_at}


@router.get("/candidates")
def candidates(page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), status: str | None = None, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    query, count = select(EvaluationCandidate), select(func.count()).select_from(EvaluationCandidate)
    if status: query, count = query.where(EvaluationCandidate.status == status), count.where(EvaluationCandidate.status == status)
    total = db.scalar(count) or 0
    rows = db.scalars(query.order_by(EvaluationCandidate.score.desc(), EvaluationCandidate.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_candidate(row) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.post("/candidates", status_code=201)
def create_candidate(payload: CandidateCreate, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row = candidate_service.create(db, query=payload.query, source_request_id=payload.source_request_id, metadata=payload.metadata)
    db.commit(); db.refresh(row)
    return _candidate(row)


@router.get("/candidates/{candidate_id}")
def candidate_detail(candidate_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row = db.get(EvaluationCandidate, candidate_id)
    if not row: raise HTTPException(404, "Evaluation candidate not found")
    return _candidate(row)


@router.post("/candidates/{candidate_id}/approve")
def approve_candidate(candidate_id: str, payload: CandidateReview, admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row = db.get(EvaluationCandidate, candidate_id)
    if not row: raise HTTPException(404, "Evaluation candidate not found")
    try: candidate_service.review(row, decision="approved", reviewer_id=admin.id, comment=payload.comment)
    except ValueError as exc: raise HTTPException(409, str(exc))
    db.commit(); return _candidate(row)


@router.post("/candidates/{candidate_id}/reject")
def reject_candidate(candidate_id: str, payload: CandidateReview, admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row = db.get(EvaluationCandidate, candidate_id)
    if not row: raise HTTPException(404, "Evaluation candidate not found")
    try: candidate_service.review(row, decision="rejected", reviewer_id=admin.id, comment=payload.comment)
    except ValueError as exc: raise HTTPException(409, str(exc))
    db.commit(); return _candidate(row)


@router.post("/candidates/{candidate_id}/add-to-dataset", status_code=201)
def add_candidate_to_dataset(candidate_id: str, payload: CandidateAdd, admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row, dataset = db.get(EvaluationCandidate, candidate_id), db.get(EvalDataset, payload.dataset_id)
    if not row: raise HTTPException(404, "Evaluation candidate not found")
    if not dataset: raise HTTPException(404, "Evaluation dataset not found")
    if row.status != "approved": raise HTTPException(409, "Candidate must be approved before dataset inclusion")
    if not payload.expected: raise HTTPException(422, "Reviewer-authored expected result is required; production output cannot be ground truth")
    next_patch = int(dataset.version.split(".")[-1]) + 1 if dataset.version.split(".")[-1].isdigit() else dataset.case_count + 1
    parts = dataset.version.split(".")
    dataset.version = ".".join(parts[:-1] + [str(next_patch)]) if len(parts) > 1 else f"{dataset.version}.{next_patch}"
    case_key = f"candidate-{candidate_id[:12]}"
    case = EvalCase(dataset_id=dataset.id, case_key=case_key, name=payload.name, category=payload.category, difficulty=payload.difficulty, tags=payload.tags, is_critical=payload.is_critical, input_text=row.query_text, expected_json=payload.expected, thresholds_json={}, source_json={"source": "human_reviewed_candidate", "candidate_id": candidate_id, "verification_status": payload.verification_status})
    db.add(case); db.flush()
    dataset.case_count += 1; row.status = "added"; row.target_dataset_id = dataset.id; row.target_case_id = case.id
    dataset_health_service.log_change(db, dataset_id=dataset.id, version=dataset.version, action="add_candidate", case_key=case_key, candidate_id=candidate_id, actor_id=admin.id, details={"verification_status": payload.verification_status})
    dataset_health_service.create_version(db, dataset, actor_id=admin.id, summary=f"Added reviewed candidate {case_key}")
    db.commit()
    return {"candidate": _candidate(row), "case_key": case_key, "dataset_id": dataset.id, "dataset_version": dataset.version}


@router.post("/runs", status_code=202)
def create_run(payload: RunCreate, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    default = ensure_default_dataset(db)
    dataset_id = payload.dataset_id or default.id
    if not db.get(EvalDataset, dataset_id): raise HTTPException(404, "Evaluation dataset not found")
    run_id = uuid.uuid4().hex
    row = EvalRun(id=run_id, name=payload.name or f"Evaluation {datetime.now():%Y-%m-%d %H:%M}", dataset_id=dataset_id, status="queued", mode=payload.mode, agent_version=payload.agent_version, model_name=payload.model or settings.DEFAULT_AGENT_MODEL, model_version=settings.VERSION, prompt_version="repository-current", embedding_model=settings.EMBEDDING_MODEL, embedding_version=settings.EMBEDDING_VERSION, retrieval_config={"candidate_k": settings.RETRIEVAL_CANDIDATE_K, "rrf_k": settings.RRF_K}, judge_model=None, judge_prompt_version="deterministic-v1", random_seed=payload.seed, config_json=payload.model_dump(mode="json"), release_gate_status="pending", release_gate_json={})
    db.add(row); db.commit()
    evaluation_runner.start(run_id)
    return _run(row)


@router.get("/runs")
def runs(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), status: str | None = None, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    ensure_default_dataset(db)
    query = select(EvalRun)
    count = select(func.count()).select_from(EvalRun)
    if status: query, count = query.where(EvalRun.status == status), count.where(EvalRun.status == status)
    total = db.scalar(count) or 0
    rows = db.scalars(query.order_by(EvalRun.created_at.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    names = {item.id: item.name for item in db.scalars(select(EvalDataset)).all()}
    return {"items": [_run(row, names.get(row.dataset_id)) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/runs/{run_id}")
def run_detail(run_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row = db.get(EvalRun, run_id)
    if not row: raise HTTPException(404, "Evaluation run not found")
    dataset = db.get(EvalDataset, row.dataset_id)
    return {**_run(row, dataset.name if dataset else None), "metrics": _metrics(db, run_id)}


@router.get("/runs/{run_id}/metrics")
def run_metrics(run_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    if not db.get(EvalRun, run_id): raise HTTPException(404, "Evaluation run not found")
    return _metrics(db, run_id)


@router.get("/runs/{run_id}/cases")
def run_cases(run_id: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), search: str | None = None, category: str | None = None, result: str | None = None, difficulty: str | None = None, critical: bool | None = None, sort: str = "case", _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    query = select(EvalCaseResult).join(EvalCase, EvalCase.id == EvalCaseResult.case_id).where(EvalCaseResult.run_id == run_id)
    count = select(func.count()).select_from(EvalCaseResult).join(EvalCase, EvalCase.id == EvalCaseResult.case_id).where(EvalCaseResult.run_id == run_id)
    conditions = []
    if search: conditions.append((EvalCase.name.contains(search)) | (EvalCase.case_key.contains(search)))
    if category: conditions.append(EvalCase.category == category)
    if result: conditions.append(EvalCaseResult.status == result.lower())
    if difficulty: conditions.append(EvalCase.difficulty == difficulty)
    if critical is not None: conditions.append(EvalCaseResult.critical == critical)
    for condition in conditions: query, count = query.where(condition), count.where(condition)
    order = EvalCaseResult.overall_score.asc() if sort == "score_asc" else (EvalCaseResult.overall_score.desc() if sort == "score_desc" else EvalCase.case_key)
    total = db.scalar(count) or 0
    rows = db.scalars(query.order_by(order).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [_case(db, row) for row in rows], "page": page, "page_size": page_size, "total": total}


@router.get("/runs/{run_id}/cases/{case_id}")
def case_detail(run_id: str, case_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    identity_condition = EvalCaseResult.id == int(case_id) if case_id.isdigit() else EvalCaseResult.id < 0
    row = db.scalar(select(EvalCaseResult).where(EvalCaseResult.run_id == run_id, (EvalCaseResult.case_key == case_id) | identity_condition))
    if not row: raise HTTPException(404, "Evaluation case result not found")
    return _case(db, row)


@router.get("/cases/{result_id}")
def case_by_result(result_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row = db.get(EvalCaseResult, result_id)
    if not row: raise HTTPException(404, "Evaluation case result not found")
    return _case(db, row)


@router.get("/runs/{run_id}/trace/{trace_id}")
def trace_detail(run_id: str, trace_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    row = db.scalar(select(EvaluationTrace).where(EvaluationTrace.id == trace_id, EvaluationTrace.run_id == run_id))
    if not row: raise HTTPException(404, "Evaluation trace not found")
    return {"id": row.id, "run_id": row.run_id, "request_id": row.request_id, "agent_version": row.agent_version, "model_name": row.model_name, "prompt_version": row.prompt_version, "input_text": row.input_text, "final_output": row.final_output, "agent_steps": row.agent_steps, "routing_history": row.routing_history, "retrievals": row.retrievals, "tool_calls": row.tool_calls, "llm_calls": row.llm_calls, "input_tokens": row.input_tokens, "output_tokens": row.output_tokens, "total_tokens": row.total_tokens, "estimated_cost": row.estimated_cost, "latency_ms": row.latency_ms, "status": row.status, "error": row.error, "metadata": row.metadata_json, "started_at": row.started_at, "ended_at": row.ended_at}


@router.get("/compare")
def compare(baseline_run_id: str, candidate_run_id: str, _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    baseline, candidate = db.get(EvalRun, baseline_run_id), db.get(EvalRun, candidate_run_id)
    if not baseline or not candidate: raise HTTPException(404, "Baseline or candidate run not found")
    case_rows = []
    for run_id in (baseline_run_id, candidate_run_id):
        case_rows.append([{**_case(db, row), "category": db.get(EvalCase, row.case_id).category} for row in db.scalars(select(EvalCaseResult).where(EvalCaseResult.run_id == run_id)).all()])
    metrics_a, metrics_b = _metrics(db, baseline_run_id), _metrics(db, candidate_run_id)
    quality_metrics = {"task_completion", "answer_quality", "rag", "tool", "routing", "trajectory", "safety", "efficiency", "faithfulness", "pass_rate"}
    names = sorted((set(metrics_a) | set(metrics_b)) & quality_metrics)
    comparison = compare_case_results(case_rows[0], case_rows[1])
    regression_drop = max([max(0, row["baseline_score"] - row["candidate_score"]) for row in comparison["cases"]] or [0])
    gate = ReleaseGate((candidate.config_json or {}).get("release_gate")).evaluate(metrics_b, critical_failures=candidate.critical_failures, regression_drop=regression_drop)
    return {"baseline": _run(baseline), "candidate": _run(candidate), "metrics": [{"metric": name, "baseline": metrics_a.get(name, 0), "candidate": metrics_b.get(name, 0), "delta": metrics_b.get(name, 0) - metrics_a.get(name, 0)} for name in names], "comparison": comparison, "release_gate": gate}


@router.get("/trends")
def trends(limit: int = Query(20, ge=1, le=100), metric: str = "overall_score", _admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    rows = list(reversed(db.scalars(select(EvalRun).where(EvalRun.status == "completed").order_by(EvalRun.created_at.desc()).limit(limit)).all()))
    return [{"run_id": row.id, "name": row.name, "date": row.finished_at or row.created_at, "value": row.overall_score if metric == "overall_score" else _metrics(db, row.id).get(metric, 0)} for row in rows]


@router.get("/dashboard")
def dashboard(_admin: User = Depends(require_admin), db: Session = Depends(get_mysql_db)):
    ensure_default_dataset(db)
    completed = list(db.scalars(select(EvalRun).where(EvalRun.status == "completed").order_by(EvalRun.created_at.desc())).all())
    latest = next((row for row in completed if (row.config_json or {}).get("architecture", "HYBRID") == "HYBRID"), completed[0] if completed else None)
    baseline = next((row for row in completed if (row.config_json or {}).get("architecture") == "SIMPLE_RAG"), None)
    recent = db.scalars(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(8)).all()
    default_dataset = ensure_default_dataset(db)
    health = dataset_health_service.calculate(db, default_dataset.id)
    live_retrieval = load_live_retrieval_report()
    pending_candidates = db.scalar(select(func.count()).select_from(EvaluationCandidate).where(EvaluationCandidate.status == "pending")) or 0
    if not latest: return {"latest_run": None, "metrics": {}, "deltas": {}, "baseline": None, "trends": [], "recent_runs": [_run(row) for row in recent], "release_gate": None, "hybrid_runtime": {"direct_rate": 0, "react_rate": 0, "multi_agent_rate": 0, "escalation_rate": 0, "routing_accuracy": 0, "execution_mode_accuracy": 0, "under_routing_rate": 0, "over_routing_rate": 0, "unnecessary_multi_agent_rate": 0, "token_savings": 0, "cost_savings": 0, "latency_savings": 0, "quality_vs_cost": []}, "dataset_health": health, "pending_candidates": pending_candidates, "live_retrieval": live_retrieval}
    previous = db.scalar(select(EvalRun).where(EvalRun.status == "completed", EvalRun.id != latest.id).order_by(EvalRun.created_at.desc()).limit(1))
    metrics = _metrics(db, latest.id); baseline_metrics = _metrics(db, baseline.id) if baseline else {}; old = baseline_metrics or (_metrics(db, previous.id) if previous else {})
    # Older completed runs predate the dedicated aggregate name.  Preserve
    # their labeled execution-mode score without claiming missing rate metrics.
    metrics["execution_mode_accuracy"] = metrics.get("execution_mode_accuracy", metrics.get("execution_mode", 0))
    live_metrics = live_retrieval.get("metrics") or {}
    comparison_before = (((live_retrieval.get("comparison") or {}).get("before") or {}).get("metrics") or {})
    live_rag = float(live_metrics.get("hit_rate_at_5", 0))
    metrics["rag_contract"] = metrics.get("rag", 0)
    metrics["rag"] = live_rag
    metrics["rag_recall_at_5"] = float(live_metrics.get("recall_at_5", 0))
    metrics["rag_precision_at_5"] = float(live_metrics.get("precision_at_5", 0))
    metrics["rag_ndcg_at_5"] = float(live_metrics.get("ndcg_at_5", 0))
    if baseline_metrics:
        baseline_metrics["rag_contract"] = baseline_metrics.get("rag", 0)
        baseline_metrics["rag"] = float(comparison_before.get("hit_rate_at_5", live_rag))
        baseline_metrics["rag_recall_at_5"] = float(comparison_before.get("recall_at_5", live_metrics.get("recall_at_5", 0)))
        baseline_metrics["rag_precision_at_5"] = float(comparison_before.get("precision_at_5", live_metrics.get("precision_at_5", 0)))
        baseline_metrics["rag_ndcg_at_5"] = float(comparison_before.get("ndcg_at_5", live_metrics.get("ndcg_at_5", 0)))
    trends_data = [{"run_id": row.id, "name": row.name, "date": row.finished_at or row.created_at, "overall_score": row.overall_score, **_metrics(db, row.id)} for row in reversed(db.scalars(select(EvalRun).where(EvalRun.status == "completed").order_by(EvalRun.created_at.desc()).limit(20)).all())]
    traces = db.scalars(select(EvaluationTrace).where(EvaluationTrace.run_id == latest.id)).all()
    modes = [str((row.metadata_json or {}).get("execution_mode", "REACT")) for row in traces]
    total = len(modes) or 1
    quality_vs_cost = [{
        "mode": mode,
        "task_completion": metrics.get(f"{key}_task_completion", 0),
        "answer_quality": metrics.get(f"{key}_answer_quality", 0),
        "avg_tokens": metrics.get(f"{key}_avg_tokens", 0),
        "avg_llm_calls": metrics.get(f"{key}_avg_llm_calls", 0),
        "avg_tool_calls": metrics.get(f"{key}_avg_tool_calls", 0),
        "avg_cost": metrics.get(f"{key}_avg_cost", 0),
        "avg_latency_ms": metrics.get(f"{key}_avg_latency_ms", 0),
    } for mode, key in (("DIRECT", "direct"), ("REACT", "react"), ("MULTI_AGENT", "multi_agent"), ("ESCALATED", "react_escalated_to_multi_agent"))]
    hybrid = {"direct_rate": sum(mode == "DIRECT" for mode in modes) / total, "react_rate": sum(mode == "REACT" for mode in modes) / total, "multi_agent_rate": sum(mode == "MULTI_AGENT" for mode in modes) / total, "escalation_rate": sum("ESCALATED" in mode for mode in modes) / total, "routing_accuracy": metrics.get("routing", 0), "execution_mode_accuracy": metrics.get("execution_mode_accuracy", metrics.get("execution_mode", 0)), "under_routing_rate": metrics.get("under_routing_rate", 0), "over_routing_rate": metrics.get("over_routing_rate", 0), "unnecessary_multi_agent_rate": metrics.get("unnecessary_multi_agent_rate", 0), "token_savings": metrics.get("token_savings", 0), "cost_savings": metrics.get("cost_savings", 0), "latency_savings": metrics.get("latency_savings", 0), "quality_vs_cost": quality_vs_cost}
    baseline_payload = None if not baseline else {"run": _run(baseline), "metrics": baseline_metrics, "definition": "Query → Retrieval Planner → Retrieve → Answer; no complexity router, tools, multi-agent collaboration, or escalation; deterministic safety checks retained.", "comparison": {name: round(metrics.get(name, 0) - baseline_metrics.get(name, 0), 6) for name in sorted(set(metrics) | set(baseline_metrics))}}
    release_gate = ReleaseGate((latest.config_json or {}).get("release_gate")).evaluate(metrics, critical_failures=latest.critical_failures)
    if live_retrieval.get("status") == "degraded":
        release_gate["status"] = "fail"
        release_gate["passed"] = False
        release_gate["reasons"].append("live_retrieval: degraded; dense embedding route unavailable")
    latest_payload = _run(latest)
    latest_payload["release_gate_status"] = release_gate["status"]
    latest_payload["release_gate"] = release_gate
    recent_payload = [_run(row) for row in recent]
    for row in recent_payload:
        if row["id"] == latest.id:
            row["release_gate_status"] = release_gate["status"]
            row["release_gate"] = release_gate
    deltas = {name: metrics.get(name, 0) - old.get(name, metrics.get(name, 0)) for name in metrics}
    return {"latest_run": latest_payload, "metrics": metrics, "deltas": deltas, "baseline": baseline_payload, "trends": trends_data, "recent_runs": recent_payload, "release_gate": release_gate, "hybrid_runtime": hybrid, "dataset_health": health, "pending_candidates": pending_candidates, "live_retrieval": live_retrieval}
