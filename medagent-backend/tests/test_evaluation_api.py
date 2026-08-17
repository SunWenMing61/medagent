from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.evaluation import router
from app.core.dependencies import require_admin
from app.db.base import MySQLBase
from app.db.session import get_mysql_db
from app.evaluation.runner import evaluation_runner
from app.models.evaluation import EvalCaseResult, EvalMetricResult, EvalRun, EvaluationTrace
import app.models  # noqa: F401


def _client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    MySQLBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    app = FastAPI()
    app.include_router(router, prefix="/api/evaluation")
    app.dependency_overrides[get_mysql_db] = lambda: factory()
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, role="admin")
    monkeypatch.setattr("app.evaluation.runner.MySQLSessionLocal", factory)
    monkeypatch.setattr(evaluation_runner, "start", lambda run_id: None)
    return TestClient(app), factory


def test_evaluation_api_create_list_and_empty_dashboard(monkeypatch):
    client, _ = _client(monkeypatch)
    datasets = client.get("/api/evaluation/datasets")
    assert datasets.status_code == 200 and datasets.json()[0]["case_count"] > 0
    created = client.post("/api/evaluation/runs", json={"dataset_id": datasets.json()[0]["id"], "mode": "FAST", "agent_version": "test", "concurrency": 1})
    assert created.status_code == 202 and created.json()["status"] == "queued"
    rows = client.get("/api/evaluation/runs").json()
    assert rows["total"] == 1 and rows["items"][0]["id"] == created.json()["id"]
    dashboard = client.get("/api/evaluation/dashboard")
    assert dashboard.status_code == 200 and dashboard.json()["latest_run"] is None


def test_evaluation_run_persists_simple_rag_architecture(monkeypatch):
    client, _ = _client(monkeypatch)
    dataset_id = client.get("/api/evaluation/datasets").json()[0]["id"]
    created = client.post("/api/evaluation/runs", json={"dataset_id":dataset_id,"mode":"FAST","architecture":"SIMPLE_RAG","agent_version":"simple-rag-v1","concurrency":1})
    assert created.status_code == 202
    assert created.json()["architecture"] == "SIMPLE_RAG"
    assert created.json()["is_baseline"] is True


def test_evaluation_api_run_case_trace_dashboard_and_compare(monkeypatch):
    client, factory = _client(monkeypatch)
    dataset_id = client.get("/api/evaluation/datasets").json()[0]["id"]
    db = factory()
    from app.models.evaluation import EvalCase
    case = db.query(EvalCase).first()
    for index, score in enumerate((.8, .9), 1):
        run_id = f"run-{index}"
        db.add(EvalRun(id=run_id, name=run_id, dataset_id=dataset_id, status="completed", mode="FAST", agent_version="v1", model_name="model", random_seed=0, retrieval_config={}, config_json={}, total_cases=1, completed_cases=1, passed_cases=1, failed_cases=0, critical_failures=0, overall_score=score, release_gate_status="pass", release_gate_json={"status":"pass","reasons":[]}))
        db.flush()
        trace_id = f"trace-{index}"
        result = EvalCaseResult(run_id=run_id, case_id=case.id, case_key=case.case_key, trace_id=trace_id, status="pass", passed=True, critical=False, overall_score=score, scores_json={"task_completion":score,"answer_quality":score,"safety":1}, actual_output="answer", details_json={}, latency_ms=10, input_tokens=1, output_tokens=1, estimated_cost=0)
        db.add(result); db.flush()
        db.add(EvaluationTrace(id=trace_id, run_id=run_id, case_result_id=result.id, request_id=trace_id, input_text="input", final_output="answer", agent_steps=[], routing_history=[], retrievals=[], tool_calls=[], llm_calls=[], input_tokens=1, output_tokens=1, total_tokens=2, estimated_cost=0, latency_ms=10, status="success", metadata_json={}, started_at=run_id == "run-1" and __import__('datetime').datetime.now() or __import__('datetime').datetime.now(), ended_at=__import__('datetime').datetime.now()))
        for metric, value in {"task_completion":score,"answer_quality":score,"rag":1,"tool":1,"faithfulness":1,"p95_latency_ms":10}.items(): db.add(EvalMetricResult(run_id=run_id,evaluator_name="test",metric_name=metric,score=value,passed=True,details_json={}))
    db.commit()
    run = client.get("/api/evaluation/runs/run-2").json()
    cases = client.get("/api/evaluation/runs/run-2/cases").json()
    assert run["metrics"]["task_completion"] == .9 and cases["total"] == 1
    assert client.get(f"/api/evaluation/cases/{cases['items'][0]['id']}").status_code == 200
    assert client.get("/api/evaluation/runs/run-2/trace/trace-2").status_code == 200
    comparison = client.get("/api/evaluation/compare", params={"baseline_run_id":"run-1","candidate_run_id":"run-2"}).json()
    assert comparison["comparison"]["summary"]["improved"] == 1
    assert client.get("/api/evaluation/dashboard").json()["latest_run"] is not None
