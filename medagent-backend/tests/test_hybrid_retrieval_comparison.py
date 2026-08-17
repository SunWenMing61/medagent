import json

from app.evaluation.hybrid_retrieval_comparison import run_hybrid_retrieval_comparison


def test_hybrid_comparison_reports_reproducible_accuracy_gain():
    report = run_hybrid_retrieval_comparison()
    assert report["dataset"]["case_count"] == 38
    assert report["dataset"]["category_count"] == 19
    assert len(report["dataset"]["sha256"]) == 64
    assert report["baseline"]["strategy"] == "dense_only"
    assert report["candidate"]["strategy"] == "dense_sparse_exact_rrf"
    assert report["candidate"]["metrics"]["accuracy_at_1"] >= report["baseline"]["metrics"]["accuracy_at_1"]
    assert report["candidate"]["metrics"]["hit_rate_at_5"] >= report["baseline"]["metrics"]["hit_rate_at_5"]
    assert report["candidate"]["metrics"]["mrr"] >= report["baseline"]["metrics"]["mrr"]
    assert report["candidate"]["metrics"]["ndcg_at_5"] >= report["baseline"]["metrics"]["ndcg_at_5"]
    assert set(report["candidate"]["by_category"]) == set(report["dataset"]["categories"])


def test_multi_relevant_metrics_include_hit_mrr_map_and_ndcg(tmp_path):
    dataset = tmp_path / "retrieval.json"
    dataset.write_text(json.dumps({
        "version": "test-v1",
        "retrieval": [{
            "id": "multi",
            "category": "test",
            "query": "target exact",
            "terms": ["target", "exact"],
            "relevance": {"r1": 2, "r2": 1},
            "candidates": [
                ["noise", "generic target", 0.95, 0.1],
                ["r1", "target exact primary", 0.7, 0.95],
                ["r2", "target exact support", 0.6, 0.9],
            ],
        }],
    }, ensure_ascii=False), encoding="utf-8")

    report = run_hybrid_retrieval_comparison(dataset)

    metrics = report["candidate"]["metrics"]
    assert metrics["hit_rate_at_1"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["recall_at_3"] == 1.0
    assert metrics["map_at_3"] == 1.0
    assert metrics["ndcg_at_3"] == 1.0
