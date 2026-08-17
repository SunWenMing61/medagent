import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import MySQLBase
from app.evaluation.candidates import candidate_service, normalize_query, semantic_similarity
from app.evaluation.contracts import CaseExecution
from app.evaluation.dataset_health import dataset_health_service, js_divergence
from app.evaluation.evaluators import ExecutionModeEvaluator
from app.hybrid.complexity_router import ComplexityRouter
from app.hybrid.context import scope_state_for_agent
from app.hybrid.contracts import ExecutionMode
from app.models.evaluation import EvalCase, EvalDataset
from app.evaluation.runner import EvaluationRunner
import app.models  # noqa: F401


def test_complexity_router_selects_simple_and_complex_paths_without_llm_tokens():
    router = ComplexityRouter()
    simple = router.route("什么是高血压？")
    complex_request = router.route("请综合指南和研究，分别比较肾功能不全老年患者使用二甲双胍与胰岛素的禁忌、剂量、相互作用和监测策略，并引用证据。")
    assert simple.execution_mode == ExecutionMode.DIRECT
    assert complex_request.execution_mode == ExecutionMode.MULTI_AGENT
    assert simple.input_tokens == simple.output_tokens == 0
    assert complex_request.score > simple.score
    assert "active_signals" in complex_request.decision_summary


def test_complexity_router_selects_react_for_single_rag_request():
    decision = ComplexityRouter().route("请查询指南并说明二甲双胍常见副作用。")
    assert decision.execution_mode == ExecutionMode.REACT
    assert decision.signals["requires_rag"] == 1


def test_router_thresholds_are_configurable():
    router = ComplexityRouter(direct_threshold=.05, multi_agent_threshold=.9)
    assert router.route("请查询指南并说明二甲双胍副作用。取消后续无关内容").execution_mode == ExecutionMode.REACT


def test_context_projection_excludes_raw_query_from_answer_agent():
    state = {"raw_query": "private", "request_id": "r", "verified_evidence": [{"id": 1}], "answer_style_preference": "concise", "retrieved_evidence": ["unverified"]}
    scoped = scope_state_for_agent(state, "answer_generation")
    assert "raw_query" not in scoped and "retrieved_evidence" not in scoped
    assert scoped["verified_evidence"] == [{"id": 1}]


def test_execution_mode_evaluator_is_deterministic():
    result = asyncio.run(ExecutionModeEvaluator().evaluate({"expected": {"execution_mode": "REACT"}}, CaseExecution(output="ok", metadata={"execution_mode": "REACT", "router_score": .2})))[0]
    assert result.passed and result.score == 1


def test_simple_rag_baseline_has_fixed_path_without_tools_or_router():
    case = type("Case", (), {"category":"rag","input_text":"blood pressure guide","source_json":{"query":"blood pressure guide","expected_routes":["local_knowledge_base"]},"expected_json":{},"is_critical":False})()
    execution = EvaluationRunner()._execute_agent(case, architecture="SIMPLE_RAG")
    assert execution.status == "success"
    assert execution.routing_history == ["simple_rag"]
    assert execution.tool_calls == []
    assert execution.metadata["architecture"] == "SIMPLE_RAG"
    assert execution.metadata["router_score"] is None


def test_complex_answer_uses_multi_agent_evidence_pipeline():
    case = type("Case", (), {"category":"complex_qa","input_text":"请综合指南和研究，比较老年肾病患者的剂量、相互作用和监测策略，并引用证据。","source_json":{"query":"请综合指南和研究，比较老年肾病患者的剂量、相互作用和监测策略，并引用证据。","evidence":[{"evidence_id":"ev-complex","content":"老年肾病患者需要剂量调整、相互作用核对和肾功能监测。","source_type":"local_knowledge_base","source_name":"guideline","retrieval_score":.95,"authority_level":9,"is_authorized":True,"is_conversation_memory":False}]},"expected_json":{},"is_critical":False})()
    execution = EvaluationRunner()._execute_agent(case, architecture="HYBRID")
    assert execution.metadata["execution_mode"] == "MULTI_AGENT"
    assert execution.routing_history == ["input_triage", "retrieval_planner", "evidence_verifier", "answer_generator_detailed"]
    assert "ev-complex" in execution.output


def test_candidate_semantic_dedup_scoring_and_dataset_health():
    engine = create_engine("sqlite://")
    MySQLBase.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    dataset = EvalDataset(id="ds", name="Living", version="1.0.0", source="database", case_count=2)
    db.add(dataset)
    db.add_all([
        EvalCase(dataset_id="ds",case_key="a",name="A",category="basic_qa",difficulty="easy",tags=[],is_critical=False,input_text="二甲双胍副作用",expected_json={"facts":["x"]},thresholds_json={},source_json={}),
        EvalCase(dataset_id="ds",case_key="b",name="B",category="safety",difficulty="hard",tags=[],is_critical=True,input_text="胸痛如何急救",expected_json={"required_content":["急救"]},thresholds_json={},source_json={}),
    ]); db.commit()
    first = candidate_service.create(db, query="二甲双胍有哪些不良反应", metadata={"status":"failed","safety_score":.6})
    db.commit()
    duplicate = candidate_service.create(db, query="二甲双胍有哪些副作用？", metadata={"status":"failed"})
    assert first.id == duplicate.id
    assert 0 <= first.score <= 1
    health = dataset_health_service.calculate(db, "ds")
    assert health["case_count"] == 2 and 0 <= health["health_score"] <= 1
    assert health["authoritative_ground_truth_rate"] == 0.0
    assert health["ground_truth_status"] == "UNTESTED"
    assert normalize_query("不良反应") == "副作用"
    assert semantic_similarity("二甲双胍不良反应", "二甲双胍副作用") > .9
    assert js_divergence({"a": 1}, {"b": 1}) == 1
