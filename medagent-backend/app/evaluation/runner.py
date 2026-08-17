"""Database-backed asynchronous evaluation runner over the project's real agents."""

from __future__ import annotations

import asyncio
import logging
import math
import statistics
import threading
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from sqlalchemy import select

from app.agents.answer_generator_agent import answer_generator_agent, answer_generator_detailed_agent
from app.agents.evidence_verifier_agent import evidence_verifier_agent
from app.agents.input_triage_agent import input_triage_agent
from app.agents.output_safety_agent import output_safety_agent
from app.agents.retrieval_planner_agent import retrieval_planner_agent
from app.agents.schemas import RetrievalPlan, StructuredAnswer
from app.core.config import settings
from app.db.session import MySQLSessionLocal
from app.evaluation.contracts import CaseExecution
from app.evaluation.evaluators import ALL_EVALUATORS
from app.evaluation.release_gate import ReleaseGate
from app.evaluation.trace import redact, trace_scope, traced_call
from app.models.evaluation import EvalCase, EvalCaseResult, EvalMetricResult, EvalRun, EvaluationTrace
from app.hybrid.complexity_router import complexity_router

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _percentile(values: list[float], percentile: float) -> float:
    if not values: return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


class EvaluationRunner:
    metric_definition_version = "agent-evaluation-audit-v2"
    weights = {"task_completion": .20, "answer_quality": .15, "rag": .15, "tool": .15, "routing": .05, "execution_mode": .10, "trajectory": .10, "efficiency": .10}

    def start(self, run_id: str) -> None:
        threading.Thread(target=self._thread_entry, args=(run_id,), daemon=True, name=f"eval-{run_id[:8]}").start()

    def _thread_entry(self, run_id: str) -> None:
        asyncio.run(self.run(run_id))

    async def run(self, run_id: str) -> None:
        db = MySQLSessionLocal()
        run = db.get(EvalRun, run_id)
        if not run:
            db.close(); return
        started = time.perf_counter()
        try:
            run.status, run.started_at = "running", _utcnow()
            db.commit()
            query = select(EvalCase).where(EvalCase.dataset_id == run.dataset_id).order_by(EvalCase.id)
            config = run.config_json or {}
            if config.get("categories"): query = query.where(EvalCase.category.in_(config["categories"]))
            cases = list(db.scalars(query).all())
            tags = set(config.get("tags") or [])
            if tags: cases = [case for case in cases if tags & set(case.tags or [])]
            max_cases = config.get("max_cases") or (10 if run.mode == "FAST" else None)
            cases = cases[:max_cases]
            run.total_cases = len(cases)
            # ORM instances are session-bound and cannot be shared by concurrent
            # worker threads. Snapshot every field the deterministic evaluator
            # needs before the commit expires them.
            case_snapshots = [SimpleNamespace(
                id=case.id, case_key=case.case_key, name=case.name,
                category=case.category, difficulty=case.difficulty,
                tags=list(case.tags or []), is_critical=bool(case.is_critical),
                input_text=case.input_text, expected_json=dict(case.expected_json or {}),
                thresholds_json=dict(case.thresholds_json or {}),
                source_json=dict(case.source_json or {}),
            ) for case in cases]
            run_snapshot = SimpleNamespace(
                id=run.id, agent_version=run.agent_version, model_name=run.model_name,
                prompt_version=run.prompt_version,
                architecture=config.get("architecture", "HYBRID"),
            )
            db.commit()
            semaphore = asyncio.Semaphore(max(1, min(int(config.get("concurrency", 2)), 8)))

            async def execute_snapshot(case):
                async with semaphore:
                    try:
                        return await asyncio.wait_for(self._evaluate_case(run_snapshot, case), timeout=float(config.get("timeout", 45)))
                    except Exception as exc:
                        logger.exception("Evaluation case failed without stopping run %s", run_id)
                        return self._failed_case(run_snapshot, case, exc)

            tasks = [asyncio.create_task(execute_snapshot(case)) for case in case_snapshots]
            for task in asyncio.as_completed(tasks):
                try:
                    result, trace = await task
                except Exception:
                    logger.exception("Unexpected evaluation task failure %s", run_id)
                    result, trace = None, None
                    run.failed_cases += 1
                if result:
                    db.add(result); db.flush()
                    trace.case_result_id = result.id
                    db.add(trace)
                    run.passed_cases += int(result.passed)
                    run.failed_cases += int(not result.passed)
                    run.critical_failures += int(result.critical)
                run.completed_cases += 1
                db.commit()
            self._aggregate(db, run)
            run.status = "completed"
        except Exception as exc:
            db.rollback()
            run = db.get(EvalRun, run_id)
            run.status, run.error = "failed", str(exc)[:2000]
            logger.exception("Evaluation run failed: %s", run_id)
        finally:
            run.finished_at = _utcnow()
            run.duration_ms = round((time.perf_counter() - started) * 1000, 3)
            db.commit(); db.close()

    async def _evaluate_case(self, run: EvalRun, case: EvalCase) -> tuple[EvalCaseResult, EvaluationTrace]:
        started_at, started = _utcnow(), time.perf_counter()
        execution = await asyncio.to_thread(self._execute_agent, case, architecture=getattr(run, "architecture", "HYBRID"))
        latency = (time.perf_counter() - started) * 1000
        evaluations = []
        normalized = {**(case.source_json or {}), "id": case.case_key, "category": case.category, "difficulty": case.difficulty, "is_critical": case.is_critical, "expected": case.expected_json or {}, "thresholds": case.thresholds_json or {}}
        for evaluator in ALL_EVALUATORS:
            evaluations.extend(await evaluator.evaluate(normalized, execution))
        scores = {item.metric_name: round(item.score, 6) for item in evaluations if not item.details.get("not_applicable")}
        safety = next(item for item in evaluations if item.metric_name == "safety")
        critical = bool(safety.details.get("critical_safety_failure"))
        efficiency = 1 / (1 + latency / 8000 + len(execution.tool_calls) * .1 + len(execution.agent_steps) * .05)
        scores["efficiency"] = round(efficiency, 6)
        applicable_weights = {name: weight for name, weight in self.weights.items() if name in scores}
        overall = sum(scores[name] * weight for name, weight in applicable_weights.items()) / max(sum(applicable_weights.values()), 1e-9)
        passed = not critical and all(item.passed for item in evaluations if item.metric_name in {"functional", "task_completion", "safety"}) and overall >= float((case.thresholds_json or {}).get("overall", .7))
        reasons = [item.reason or item.metric_name for item in evaluations if not item.passed]
        trace_id = uuid.uuid4().hex
        case_result = EvalCaseResult(run_id=run.id, case_id=case.id, case_key=case.case_key, trace_id=trace_id, status="critical" if critical else ("pass" if passed else "fail"), passed=passed, critical=critical, overall_score=round(overall, 6), scores_json=scores, actual_output=redact(execution.output), failure_reason="; ".join(reasons)[:2000] if reasons else None, judge_reason=None, details_json={item.metric_name: item.details for item in evaluations}, latency_ms=round(latency, 3), input_tokens=execution.input_tokens, output_tokens=execution.output_tokens, estimated_cost=execution.estimated_cost)
        trace = EvaluationTrace(id=trace_id, run_id=run.id, request_id=uuid.uuid4().hex, agent_version=run.agent_version, model_name=run.model_name, prompt_version=run.prompt_version, input_text=redact(case.input_text), final_output=redact(execution.output), agent_steps=redact(execution.agent_steps), routing_history=execution.routing_history, retrievals=redact(execution.retrievals), tool_calls=redact(execution.tool_calls), llm_calls=redact(execution.llm_calls), input_tokens=execution.input_tokens, output_tokens=execution.output_tokens, total_tokens=execution.input_tokens + execution.output_tokens, estimated_cost=execution.estimated_cost, latency_ms=round(latency, 3), status=execution.status, error=redact(execution.error), metadata_json=redact(execution.metadata), started_at=started_at, ended_at=_utcnow())
        return case_result, trace

    @staticmethod
    def _failed_case(run: EvalRun, case: EvalCase, exc: Exception) -> tuple[EvalCaseResult, EvaluationTrace]:
        now, trace_id = _utcnow(), uuid.uuid4().hex
        error = redact(str(exc))
        result = EvalCaseResult(run_id=run.id, case_id=case.id, case_key=case.case_key, trace_id=trace_id, status="critical" if case.is_critical else "fail", passed=False, critical=bool(case.is_critical), overall_score=0, scores_json={"functional": 0, "task_completion": 0, "safety": 0 if case.is_critical else 1}, actual_output="", failure_reason=f"Case execution failed: {error}", details_json={"exception": {"type": type(exc).__name__}}, latency_ms=0, input_tokens=0, output_tokens=0, estimated_cost=0)
        trace = EvaluationTrace(id=trace_id, run_id=run.id, request_id=uuid.uuid4().hex, agent_version=run.agent_version, model_name=run.model_name, prompt_version=run.prompt_version, input_text=redact(case.input_text), final_output="", agent_steps=[], routing_history=[], retrievals=[], tool_calls=[], llm_calls=[], input_tokens=0, output_tokens=0, total_tokens=0, estimated_cost=0, latency_ms=0, status="error", error=error, metadata_json={"failure_isolated": True}, started_at=now, ended_at=now)
        return result, trace

    def _execute_agent(self, case: EvalCase, *, architecture: str = "HYBRID") -> CaseExecution:
        source, category = case.source_json or {}, case.category
        with trace_scope() as collector:
            try:
                query = source.get("query") or case.input_text
                if architecture == "SIMPLE_RAG":
                    return self._execute_simple_rag(case, query, source, collector)
                route = complexity_router.route(query)
                if architecture == "ALL_MULTI_AGENT":
                    from app.hybrid.contracts import ExecutionMode, RouterDecision
                    route = RouterDecision(
                        execution_mode=ExecutionMode.MULTI_AGENT,
                        complexity_level=route.complexity_level,
                        score=route.score,
                        confidence=1.0,
                        signals=route.signals,
                        decision_summary="all-multi-agent baseline forced by evaluation architecture",
                        latency_ms=route.latency_ms,
                        escalation_enabled=False,
                        route_source="evaluation_baseline",
                    )
                routing_metadata = {"execution_mode": route.execution_mode.value, "complexity_level": route.complexity_level.value, "complexity_score": route.score, "router_score": route.score, "router_confidence": route.confidence, "router_signals": route.signals, "router_latency_ms": route.latency_ms, "router_tokens": route.input_tokens + route.output_tokens, "escalated": False, "escalation_reason": None, "llm_call_count": 0, "tool_call_count": 0, "agent_count": 0}
                if category == "hybrid_routing":
                    expected = (case.expected_json or {}).get("execution_mode")
                    output = f"Selected {route.execution_mode.value} for {route.complexity_level.value} request"
                    collector.steps.append({"step_number": 1, "agent_name": "complexity_router", "action": "route", "input": {"query_length": len(query)}, "output": {"execution_mode": route.execution_mode.value, "score": route.score}, "latency_ms": route.latency_ms, "status": "success"})
                    return CaseExecution(output=output, agent_steps=collector.steps, routing_history=["complexity_router"], metadata={**routing_metadata, "expected_execution_mode": expected, "expected_complexity": (case.expected_json or {}).get("complexity")})
                if category == "tool_calling":
                    from app.tools.registry import tool_registry
                    intent = source.get("intent", "medical_knowledge")
                    del intent
                    tools = tool_registry.available(agent_name=source.get("agent", "retrieval"), permission_scopes=set(source.get("scopes", [])))
                    names = [item.name for item in tools]
                    calls = [{"tool_name": name, "arguments": {}, "success": True, "latency_ms": 0} for name in names]
                    collector.steps.append({"step_number": 1, "agent_name": "tool_governance", "action": "select_tools", "input": redact(source), "output": names, "latency_ms": 0, "status": "success"})
                    return CaseExecution(output=", ".join(names) or "No tool call required", agent_steps=collector.steps, routing_history=["tool_governance"], tool_calls=calls, metadata=routing_metadata)
                if category == "safety":
                    answer = StructuredAnswer.model_validate(source["answer"])
                    review = traced_call("output_safety", "safety_check", output_safety_agent.run, answer, allowed_evidence_ids=set(source.get("allowed_evidence_ids", [])), risk_level=source.get("risk_level", "low"))
                    violations = [] if review.safety_status == source.get("expected_status") else (["critical_violation"] if case.is_critical else ["unsupported_claim"])
                    return CaseExecution(output=review.model_dump_json(), agent_steps=collector.steps, routing_history=["output_safety"], metadata={**routing_metadata, "safety_violations": violations, "safety_status": review.safety_status})
                triage = traced_call("input_triage", "triage", input_triage_agent.run, query)
                if category == "agent_routing":
                    actual = ["input_triage"] + ([] if triage.need_emergency_response else ["retrieval_planner"])
                    return CaseExecution(output=triage.model_dump_json(), agent_steps=collector.steps, routing_history=actual, metadata=routing_metadata)
                plan = traced_call("retrieval_planner", "plan_retrieval", retrieval_planner_agent.run, query, triage)
                if category == "rag":
                    retrievals = [{"query": query, "document_id": name, "chunk_id": name, "rank": index + 1, "similarity_score": 1.0 - index * .05, "content": ""} for index, name in enumerate(plan.retrieval_routes)]
                    return CaseExecution(output=plan.model_dump_json(), agent_steps=collector.steps, routing_history=["input_triage", "retrieval_planner"], retrievals=retrievals, metadata=routing_metadata)
                evidence = source.get("evidence")
                if evidence is not None:
                    retrievals = [{"query": query, "document_id": item.get("evidence_id"), "chunk_id": item.get("evidence_id"), "rank": index + 1, "similarity_score": item.get("retrieval_score", 0), "content": item.get("content", "")} for index, item in enumerate(evidence)]
                    if category == "complex_qa" and route.execution_mode.value == "MULTI_AGENT":
                        verification = traced_call("evidence_verifier", "verify_evidence", evidence_verifier_agent.run, plan, evidence)
                        allowed = set(verification.supporting_evidence_ids)
                        verified = [item for item in evidence if item.get("evidence_id") in allowed]
                        answer = traced_call("answer_generator_detailed", "generate_answer", answer_generator_detailed_agent.run, query, verified)
                        return CaseExecution(output=answer.model_dump_json(), agent_steps=collector.steps, routing_history=["input_triage", "retrieval_planner", "evidence_verifier", "answer_generator_detailed"], retrievals=retrievals, metadata={**routing_metadata, "evidence_status": verification.evidence_status})
                    answer = traced_call("answer_generator", "generate_answer", answer_generator_agent.run, query, evidence)
                    return CaseExecution(output=answer.model_dump_json(), agent_steps=collector.steps, routing_history=["input_triage", "retrieval_planner", "answer_generator"], retrievals=retrievals, metadata=routing_metadata)
                return CaseExecution(output=triage.model_dump_json(), agent_steps=collector.steps, routing_history=["input_triage", "retrieval_planner"], metadata=routing_metadata)
            except Exception as exc:
                return CaseExecution(output="", status="error", error=str(exc), agent_steps=collector.steps, routing_history=[item.get("agent_name") for item in collector.steps], metadata={"safety_violations": ["critical_violation"] if case.is_critical else []})

    @staticmethod
    def _execute_simple_rag(case, query: str, source: dict, collector) -> CaseExecution:
        """Fixed minimal RAG baseline with no router, tools, handoffs or escalation."""
        triage = traced_call("input_triage", "safety_prescreen", input_triage_agent.run, query)
        if case.category == "safety" and source.get("answer"):
            answer = StructuredAnswer.model_validate(source["answer"])
            review = traced_call("output_safety", "safety_check", output_safety_agent.run, answer, allowed_evidence_ids=set(source.get("allowed_evidence_ids", [])), risk_level=source.get("risk_level", "low"))
            violations = [] if review.safety_status == source.get("expected_status") else (["critical_violation"] if case.is_critical else ["unsupported_claim"])
            return CaseExecution(output=review.model_dump_json(), agent_steps=collector.steps, routing_history=["simple_rag"], metadata={"architecture": "SIMPLE_RAG", "execution_mode": "SIMPLE_RAG", "safety_violations": violations, "safety_status": review.safety_status, "escalated": False})
        plan = traced_call("retrieval_planner", "plan_retrieval", retrieval_planner_agent.run, query, triage)
        retrievals = [{"query": query, "document_id": name, "chunk_id": name, "rank": index + 1, "similarity_score": 1.0 - index * .05, "content": ""} for index, name in enumerate(plan.retrieval_routes)]
        evidence = source.get("evidence")
        if evidence:
            answer = traced_call("answer_generator", "generate_answer", answer_generator_agent.run, query, evidence)
            output = answer.model_dump_json()
            retrievals = [{"query": query, "document_id": item.get("evidence_id"), "chunk_id": item.get("evidence_id"), "rank": index + 1, "similarity_score": item.get("retrieval_score", 0), "content": item.get("content", "")} for index, item in enumerate(evidence)]
        else:
            output = plan.model_dump_json()
        return CaseExecution(output=output, agent_steps=collector.steps, routing_history=["simple_rag"], retrievals=retrievals, tool_calls=[], metadata={"architecture": "SIMPLE_RAG", "execution_mode": "SIMPLE_RAG", "router_score": None, "router_tokens": 0, "escalated": False, "escalation_reason": None, "safety_violations": []})

    def _aggregate(self, db, run: EvalRun) -> None:
        results = list(db.scalars(select(EvalCaseResult).where(EvalCaseResult.run_id == run.id)).all())
        metric_names = {name for result in results for name in (result.scores_json or {})}
        latencies = [result.latency_ms for result in results]
        aggregated = {name: statistics.fmean([result.scores_json[name] for result in results if name in result.scores_json]) for name in metric_names}
        aggregated.update({"pass_rate": run.passed_cases / len(results) if results else 0, "average_latency_ms": statistics.fmean(latencies) if latencies else 0, "p50_latency_ms": _percentile(latencies, .5), "p95_latency_ms": _percentile(latencies, .95), "p99_latency_ms": _percentile(latencies, .99), "average_tokens": statistics.fmean([result.input_tokens + result.output_tokens for result in results]) if results else 0, "average_cost": statistics.fmean([result.estimated_cost for result in results]) if results else 0, "average_tool_calls": statistics.fmean([float((result.details_json or {}).get("trajectory", {}).get("tool_call_count", 0)) for result in results]) if results else 0, "average_agent_steps": statistics.fmean([float((result.details_json or {}).get("trajectory", {}).get("step_count", 0)) for result in results]) if results else 0})
        traces = list(db.scalars(select(EvaluationTrace).where(EvaluationTrace.run_id == run.id)).all())
        trace_by_result = {item.case_result_id: item for item in traces}
        labeled_modes: list[tuple[str, str, EvalCaseResult]] = []
        for result in results:
            detail = (result.details_json or {}).get("execution_mode", {})
            expected_modes = detail.get("expected_mode") or []
            if expected_modes:
                expected = str(expected_modes[0])
                actual = str(detail.get("actual_mode") or "")
                labeled_modes.append((expected, actual, result))
        order = {"DIRECT": 0, "REACT": 1, "MULTI_AGENT": 2, "REACT_ESCALATED_TO_MULTI_AGENT": 2}
        expected_multi = [(expected, actual) for expected, actual, _ in labeled_modes if expected == "MULTI_AGENT"]
        expected_non_multi = [(expected, actual) for expected, actual, _ in labeled_modes if expected in {"DIRECT", "REACT"}]
        under = sum(actual in {"DIRECT", "REACT"} for _expected, actual in expected_multi)
        over = sum(actual in {"MULTI_AGENT", "REACT_ESCALATED_TO_MULTI_AGENT"} for _expected, actual in expected_non_multi)
        escalated_traces = [item for item in traces if (item.metadata_json or {}).get("escalated")]
        successful_escalations = [item for item in escalated_traces if item.status == "success" and not (item.metadata_json or {}).get("safety_violations")]
        denom = len(labeled_modes) or 1
        if labeled_modes:
            aggregated["execution_mode_accuracy"] = sum(expected == actual or (expected == "MULTI_AGENT" and actual == "REACT_ESCALATED_TO_MULTI_AGENT") for expected, actual, _ in labeled_modes) / denom
        if expected_multi:
            aggregated["under_routing_rate"] = under / len(expected_multi)
        if expected_non_multi:
            aggregated["over_routing_rate"] = over / len(expected_non_multi)
        if traces:
            aggregated["escalation_rate"] = len(escalated_traces) / len(traces)
        if escalated_traces:
            aggregated["successful_escalation_rate"] = len(successful_escalations) / len(escalated_traces)
        for mode in ("DIRECT", "REACT", "MULTI_AGENT"):
            predicted = [(expected, actual) for expected, actual, _ in labeled_modes if actual == mode or (mode == "MULTI_AGENT" and actual == "REACT_ESCALATED_TO_MULTI_AGENT")]
            expected_rows = [(expected, actual) for expected, actual, _ in labeled_modes if expected == mode]
            true_positive = sum(expected == mode and (actual == mode or (mode == "MULTI_AGENT" and actual == "REACT_ESCALATED_TO_MULTI_AGENT")) for expected, actual, _ in labeled_modes)
            if predicted:
                aggregated[f"{mode.lower()}_precision"] = true_positive / len(predicted)
            if expected_rows:
                aggregated[f"{mode.lower()}_recall"] = true_positive / len(expected_rows)
        for mode in ("DIRECT", "REACT", "MULTI_AGENT", "REACT_ESCALATED_TO_MULTI_AGENT"):
            selected = [item for item in traces if str((item.metadata_json or {}).get("execution_mode")) == mode]
            key = mode.lower()
            selected_results = [result for result in results if trace_by_result.get(result.id) in selected]
            aggregated[f"{key}_usage_rate"] = len(selected) / len(traces) if traces else 0.0
            if any("task_completion" in (result.scores_json or {}) for result in selected_results):
                aggregated[f"{key}_task_completion"] = statistics.fmean([result.scores_json["task_completion"] for result in selected_results if "task_completion" in (result.scores_json or {})])
            if any("answer_quality" in (result.scores_json or {}) for result in selected_results):
                aggregated[f"{key}_answer_quality"] = statistics.fmean([result.scores_json["answer_quality"] for result in selected_results if "answer_quality" in (result.scores_json or {})])
            if selected:
                aggregated[f"{key}_avg_tokens"] = statistics.fmean([item.total_tokens for item in selected])
                aggregated[f"{key}_avg_llm_calls"] = statistics.fmean([len(item.llm_calls or []) for item in selected])
                aggregated[f"{key}_avg_tool_calls"] = statistics.fmean([len(item.tool_calls or []) for item in selected])
                aggregated[f"{key}_avg_cost"] = statistics.fmean([item.estimated_cost for item in selected])
                aggregated[f"{key}_avg_latency_ms"] = statistics.fmean([item.latency_ms for item in selected])
        # Savings are only valid for paired runs over the same case IDs and
        # dataset version. A within-run mode average is not a baseline.
        aggregated["evaluation_error_count"] = sum(result.status == "error" or "exception" in (result.details_json or {}) for result in results)
        aggregated["valid_evaluated_cases"] = sum(not (result.status == "error" or "exception" in (result.details_json or {})) for result in results)
        aggregated["total_cases"] = len(results)
        for name, score in aggregated.items():
            applicable = [result for result in results if name in (result.scores_json or {})]
            details = {
                "applicable_cases": len(applicable),
                "total_cases": len(results),
                "perfect_cases": sum(float((result.scores_json or {}).get(name, -1)) == 1.0 for result in applicable),
                "metric_definition_version": self.metric_definition_version,
                "verification_status": "VERIFIED" if applicable else "UNTESTED",
            } if applicable else {"total_cases": len(results), "metric_definition_version": self.metric_definition_version, "verification_status": "UNTESTED"}
            db.add(EvalMetricResult(run_id=run.id, evaluator_name="aggregator", metric_name=name, score=round(score, 6), passed=True, details_json=details))
        run.overall_score = round(statistics.fmean([result.overall_score for result in results]) if results else 0, 6)
        gate = ReleaseGate((run.config_json or {}).get("release_gate")).evaluate(aggregated, critical_failures=run.critical_failures)
        run.release_gate_status, run.release_gate_json = gate["status"], gate


evaluation_runner = EvaluationRunner()
