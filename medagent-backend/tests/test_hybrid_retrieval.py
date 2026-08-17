"""Hybrid retrieval state, fusion, scoping and evidence-budget tests."""

import pytest

from app.services.retrieval_service import (
    HybridRetriever,
    RetrievalScopeError,
    RetrievalStatus,
    reciprocal_rank_fusion,
)
from app.tools.schemas import LocalRetrievalInput, ToolContext


class _IdentityReranker:
    def rerank(self, query, chunks, top_k, threshold):
        del query, threshold
        return chunks[:top_k]


def _candidate(chunk_id, score=1.0, content="evidence", parent_id=None):
    return {
        "id": chunk_id,
        "document_id": 10,
        "kb_id": 3,
        "chunk_index": chunk_id,
        "content": content,
        "page_num": 1,
        "parent_chunk_id": parent_id,
        "content_sha256": f"hash-{chunk_id}",
        "similarity": score,
    }


def test_empty_scope_fails_closed():
    retriever = HybridRetriever(lambda *_: [], lambda *_: [], reranker=_IdentityReranker())
    with pytest.raises(RetrievalScopeError):
        retriever.retrieve("query", [])


def test_lexical_fallback_is_degraded_not_no_evidence():
    def dense(*_args):
        raise TimeoutError("embedding provider unavailable")

    retriever = HybridRetriever(
        dense, lambda *_: [_candidate(1)], parent_fetcher=lambda _ids: {},
        reranker=_IdentityReranker(),
    )
    result = retriever.retrieve("query", [3])
    assert result.status == RetrievalStatus.DEGRADED
    assert [item["id"] for item in result.evidence] == [1]
    assert result.issues[0].component == "dense"


def test_both_backends_failing_is_error_not_empty_success():
    def fail(*_args):
        raise ConnectionError("database unavailable")

    result = HybridRetriever(fail, fail, reranker=_IdentityReranker()).retrieve("query", [1])
    assert result.status == RetrievalStatus.ERROR
    assert result.evidence == []
    assert len(result.issues) == 2


def test_successful_empty_rankings_mean_no_evidence():
    result = HybridRetriever(
        lambda *_: [], lambda *_: [], reranker=_IdentityReranker()
    ).retrieve("query", [1])
    assert result.status == RetrievalStatus.NO_EVIDENCE
    assert not result.issues


def test_rrf_rewards_candidates_seen_by_both_retrievers():
    fused = reciprocal_rank_fusion(
        [[_candidate(1), _candidate(2)], [_candidate(2), _candidate(3)]], rrf_k=60
    )
    assert fused[0]["id"] == 2
    assert fused[0]["retrieval_sources"] == [0, 1]


def test_parent_expansion_and_token_budget_are_bounded():
    items = [_candidate(1, parent_id=100), _candidate(2, content="second")]
    retriever = HybridRetriever(
        lambda *_: items, lambda *_: [],
        parent_fetcher=lambda ids: {100: "parent context with more details"},
        reranker=_IdentityReranker(),
    )
    result = retriever.retrieve("query", [3], top_k=1, evidence_token_budget=20)
    assert result.status == RetrievalStatus.OK
    assert len(result.evidence) == 1
    assert result.evidence[0]["context_content"] == "parent context with more details"


def test_local_tool_delegates_final_k_to_query_aware_hybrid_policy():
    payload = LocalRetrievalInput(
        context=ToolContext(request_id="req-test", user_id=1, tenant_id=1, authorized_kb_ids=[3]),
        query="hypertension review",
    )
    assert payload.top_k is None


def test_dynamic_final_k_replaces_fixed_top_five(monkeypatch):
    monkeypatch.setattr("app.services.retrieval_service.settings.EVIDENCE_MAX_CHUNKS", 12)
    items = [_candidate(index, content=f"evidence {index}") for index in range(1, 16)]
    retriever = HybridRetriever(
        lambda *_: items,
        lambda *_: list(reversed(items)),
        parent_fetcher=lambda _ids: {},
        reranker=_IdentityReranker(),
    )

    assert len(retriever.retrieve("basic question", [3]).evidence) == 5
    assert len(retriever.retrieve("drug interaction", [3]).evidence) == 8
    assert len(retriever.retrieve("systematic review compare", [3]).evidence) == 12
