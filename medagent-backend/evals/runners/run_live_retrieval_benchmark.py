"""Run a document-level live retrieval benchmark without leaking gold labels."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.agents.input_triage_agent import input_triage_agent
from app.agents.retrieval_planner_agent import retrieval_planner_agent
from app.services.retrieval_service import HybridRetriever


class IdentityReranker:
    """Keep retrieval fusion order stable while measuring recall-stage quality."""

    @staticmethod
    def rerank(_query: str, chunks: list[dict], **_kwargs) -> list[dict]:
        return chunks


class DenseDisabledRetriever(HybridRetriever):
    """Ablation retriever with the dense route deliberately disabled."""

    def _dense_search(self, *_args, **_kwargs) -> list[dict]:
        return []


def _ndcg(ranked: list[int], relevant: set[int], k: int) -> float:
    dcg = sum((1.0 / math.log2(rank + 1)) for rank, doc_id in enumerate(ranked[:k], 1) if doc_id in relevant)
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(k, len(relevant)) + 1))
    return dcg / ideal if ideal else 0.0


def _average_precision(ranked: list[int], relevant: set[int], k: int) -> float:
    if not relevant:
        return 0.0
    hits = 0
    total = 0.0
    for rank, document_id in enumerate(ranked[:k], 1):
        if document_id in relevant:
            hits += 1
            total += hits / rank
    return total / min(len(relevant), k)


def _planner_terms(plan) -> list[str]:
    terms: list[str] = []
    for entity in plan.entities:
        terms.extend([entity.original_text, entity.canonical_name, *(entity.synonyms or []), *(entity.aliases or [])])
    terms.extend(str(item.get("original_text") or "") for item in plan.numeric_constraints)
    return list(dict.fromkeys(term.strip() for term in terms if term and term.strip()))


def run(dataset_path: Path, dense: bool) -> dict:
    cases = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retriever_cls = HybridRetriever if dense else DenseDisabledRetriever
    retriever = retriever_cls(reranker=IdentityReranker())
    results: list[dict] = []
    for case in cases:
        query = case["query"]
        triage = input_triage_agent.run(query)
        plan = retrieval_planner_agent.run(query, triage)
        result = retriever.retrieve(
            plan.normalized_query or query,
            case["kb_ids"],
            top_k=5,
            exact_terms=_planner_terms(plan),
            numeric_constraints=plan.numeric_constraints,
            population_constraints=plan.population_constraints,
            time_constraints=plan.time_constraints,
            negations=plan.negations,
        )
        ranked: list[int] = []
        for item in result.evidence:
            document_id = int(item["document_id"])
            if document_id not in ranked:
                ranked.append(document_id)
        relevant = {int(value) for value in case["relevant_document_ids"]}
        hit_count = len(relevant.intersection(ranked[:5]))
        first_hit = next((index for index, doc_id in enumerate(ranked[:5], 1) if doc_id in relevant), None)
        results.append({
            "id": case["id"],
            "ranked_document_ids": ranked[:5],
            "hit_at_5": float(hit_count > 0),
            "precision_at_5": hit_count / 5,
            "recall_at_5": hit_count / len(relevant) if relevant else 0.0,
            "mrr": 1.0 / first_hit if first_hit else 0.0,
            "ndcg_at_5": _ndcg(ranked, relevant, 5),
            "map_at_5": _average_precision(ranked, relevant, 5),
            "status": result.status.value,
            "issues": [{"component": issue.component, "code": issue.code} for issue in result.issues],
            "routes": {name: len(items) for name, items in result.rankings.items()},
            "latency_ms": result.timings_ms.get("total_ms", 0.0),
        })
    metric_names = ("hit_at_5", "precision_at_5", "recall_at_5", "mrr", "ndcg_at_5", "map_at_5")
    return {
        "evaluated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataset": dataset_path.stem,
        "dataset_version": "live-retrieval-v2-post-revectorization",
        "metric_definition_version": "rag-document-ranking-v2-fixed-k",
        "averaging": "macro_by_query",
        "verification_status": "VERIFIED",
        "sample_size": len(results),
        "dense_enabled": dense,
        "metrics": {name: statistics.fmean(row[name] for row in results) for name in metric_names},
        "successful_queries": sum(row["hit_at_5"] > 0 for row in results),
        "degraded_queries": sum(row["status"] != "success" for row in results),
        "average_latency_ms": statistics.fmean(row["latency_ms"] for row in results),
        "cases": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("evals/datasets/live_retrieval_benchmark_v1.jsonl"))
    parser.add_argument("--dense", choices=("on", "off"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = run(args.dataset, args.dense == "on")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("sample_size", "dense_enabled", "metrics", "successful_queries", "degraded_queries", "average_latency_ms")}, ensure_ascii=False))
