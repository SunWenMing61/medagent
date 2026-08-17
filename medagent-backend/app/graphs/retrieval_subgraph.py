"""Parallel retrieval subgraph with deterministic normalization and fusion."""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed

from langgraph.graph import END, START, StateGraph

from app.agents.schemas import RetrievalPlan
from app.chunking.token_counter import count_tokens
from app.core.config import settings
from app.graphs.graph_state import AgentGraphState
from app.tools.schemas import LocalRetrievalInput, OnlineRetrievalInput, ToolContext


def build_retrieval_subgraph(runtime):
    def _context(state: dict) -> ToolContext:
        return ToolContext(
            request_id=state["request_id"],
            user_id=state["user_id"],
            tenant_id=state["tenant_id"],
            authorized_kb_ids=state["authorized_kb_ids"],
        )

    def local_retrieval_node(state: dict, plan: RetrievalPlan):
        if "local_knowledge_base" not in plan.retrieval_routes:
            return None
        if not state.get("authorized_kb_ids"):
            return {"status": "no_result", "evidence": [], "message": "No authorized local KB scope."}
        query = plan.local_queries[0] if plan.local_queries else plan.normalized_query
        if int(state.get("retrieval_retry_count", 0)):
            query = f"{query} guideline evidence"
        exact_terms = [item.original_text for item in plan.entities]
        return runtime.run_tool(state, "local_knowledge_base", LocalRetrievalInput(
            context=_context(state), query=query, exact_terms=exact_terms,
            numeric_constraints=plan.numeric_constraints,
            population_constraints=plan.population_constraints,
            time_constraints=plan.time_constraints,
            negations=plan.negations,
        ))

    def online_retrieval_node(state: dict, plan: RetrievalPlan):
        routes = [item for item in plan.retrieval_routes if item in {"web_search", "pubmed", "fda_drug_label", "msd_manual"}]
        if not routes:
            return []
        query = plan.online_queries[0] if plan.online_queries else plan.normalized_query
        results = []
        for route in routes:
            if route == "web_search" and not settings.ENABLE_GENERAL_WEB_SEARCH:
                results.append({"status": "error", "evidence": [], "error_code": "WEB_SEARCH_DISABLED", "message": "General web search is disabled."})
                continue
            if route != "web_search" and not settings.ENABLE_ONLINE_MEDICAL_SEARCH:
                results.append({"status": "error", "evidence": [], "error_code": "ONLINE_MEDICAL_SEARCH_DISABLED", "message": "Online medical search is disabled."})
                continue
            results.append(runtime.run_tool(state, route, OnlineRetrievalInput(
                context=_context(state), query=query, max_results=min(plan.max_candidates_per_route, 10),
            )))
        return results

    def parallel_retrieval(state: AgentGraphState) -> dict:
        updated = dict(state)
        plan = RetrievalPlan.model_validate(updated["retrieval_plan"])
        runtime.public_event(updated, "retrieval_started", {"routes": plan.retrieval_routes})
        outputs: dict[str, object] = {}
        jobs = {
            "local": lambda: local_retrieval_node(updated, plan),
            "online": lambda: online_retrieval_node(updated, plan),
        }
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="controlled-retrieval") as pool:
            futures = {pool.submit(function): name for name, function in jobs.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    outputs[name] = future.result()
                except Exception as exc:
                    outputs[name] = {"status": "error", "evidence": [], "error_code": f"{name.upper()}_ERROR", "message": str(exc)}

        local = outputs.get("local")
        online = outputs.get("online") or []
        local_dict = local.model_dump(mode="json") if hasattr(local, "model_dump") else (local or {})
        online_dicts = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in online]
        updated["local_evidence"] = list(local_dict.get("evidence", []))
        updated["online_evidence"] = [evidence for item in online_dicts for evidence in item.get("evidence", [])]
        issues = []
        for source, item in [("local", local_dict), *[("online", entry) for entry in online_dicts]]:
            if item and item.get("status") in {"error", "timeout", "forbidden", "partial"}:
                error = item.get("error") or {}
                issues.append({
                    "component": source,
                    "error_code": error.get("code") or item.get("error_code"),
                    "message": error.get("message") or item.get("message"),
                    "status": item.get("status"),
                })
        updated["retrieval_issues"] = issues
        return updated

    def result_normalization_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        candidates = []
        for source_index, group in enumerate((updated.get("local_evidence", []), updated.get("online_evidence", []))):
            for rank, evidence in enumerate(group, start=1):
                item = dict(evidence)
                item["rrf_score"] = float(item.get("rrf_score") or 0.0) + 1.0 / (settings.RRF_K + rank)
                item.setdefault("metadata", {})["source_index"] = source_index
                candidates.append(item)
        updated["candidate_evidence"] = candidates
        return updated

    def deduplication_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        deduplicated = []
        seen = set()
        for item in updated.get("candidate_evidence", []):
            key = item.get("url") or hashlib.sha256(item.get("content", "").encode("utf-8")).hexdigest()
            if key not in seen:
                seen.add(key)
                deduplicated.append(item)
        updated["candidate_evidence"] = deduplicated
        return updated

    def fusion_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        updated["candidate_evidence"] = sorted(
            updated.get("candidate_evidence", []),
            key=lambda item: (-float(item.get("rrf_score") or 0), -int(item.get("authority_level") or 0)),
        )
        return updated

    def rerank_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        query_terms = {item.lower() for item in updated.get("normalized_query", "").split() if item}
        for item in updated.get("candidate_evidence", []):
            content_terms = {value.lower() for value in item.get("content", "").split() if value}
            overlap = len(query_terms & content_terms) / max(len(query_terms), 1)
            item["rerank_score"] = max(float(item.get("rerank_score") or 0), overlap)
        updated["candidate_evidence"] = sorted(
            updated.get("candidate_evidence", []),
            key=lambda item: (-float(item.get("exact_match_score") or 0), -float(item.get("rerank_score") or 0), -int(item.get("authority_level") or 0)),
        )
        return updated

    def retrieval_result_node(state: AgentGraphState) -> dict:
        updated = dict(state)
        selected = []
        tokens = 0
        for item in updated.get("candidate_evidence", []):
            item_tokens = count_tokens(item.get("content", ""))
            if selected and tokens + item_tokens > settings.EVIDENCE_MAX_TOKENS:
                continue
            selected.append(item)
            tokens += item_tokens
            if len(selected) >= settings.EVIDENCE_MAX_CHUNKS:
                break
        updated["retrieved_evidence"] = selected
        updated["retrieval_results"] = list(selected)
        updated["current_agent"] = "retrieval"
        updated.setdefault("completed_agents", []).append("retrieval_subgraph")
        runtime.public_event(updated, "retrieval_completed", {
            "evidence_count": len(selected), "issue_count": len(updated.get("retrieval_issues", [])),
        })
        runtime.checkpoint(updated, "retrieval")
        return updated

    graph = StateGraph(AgentGraphState)
    graph.add_node("parallel_retrieval", parallel_retrieval)
    graph.add_node("result_normalization", result_normalization_node)
    graph.add_node("deduplication", deduplication_node)
    graph.add_node("fusion", fusion_node)
    graph.add_node("rerank", rerank_node)
    graph.add_node("retrieval_result", retrieval_result_node)
    graph.add_edge(START, "parallel_retrieval")
    graph.add_edge("parallel_retrieval", "result_normalization")
    graph.add_edge("result_normalization", "deduplication")
    graph.add_edge("deduplication", "fusion")
    graph.add_edge("fusion", "rerank")
    graph.add_edge("rerank", "retrieval_result")
    graph.add_edge("retrieval_result", END)
    return graph.compile()
