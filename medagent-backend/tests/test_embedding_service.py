"""Embedding batching, retry, dimension and cache regression tests."""

import httpx
import pytest

from app.services.embedding_service import (
    EmbeddingDimensionError,
    EmbeddingProviderUnavailableError,
    EmbeddingService,
    EmbeddingTransientError,
)


def _service(handler, **kwargs):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return EmbeddingService(
        client=client,
        api_key="test-key",
        api_base="https://embedding.test/v1/embeddings",
        model="test-model",
        dimensions=3,
        version="test-v1",
        batch_size=2,
        random_value=lambda: 0.0,
        **kwargs,
    )


def test_batching_preserves_order_and_uses_cache():
    calls = []

    def handler(request):
        payload = __import__("json").loads(request.content)
        calls.append(payload["input"])
        return httpx.Response(
            200,
            json={"data": [
                {"index": index, "embedding": [float(len(text)), float(index), 1.0]}
                for index, text in enumerate(payload["input"])
            ]},
        )

    service = _service(handler)
    first = service.embed_batch(["a", "bb", "ccc"]).require_all()
    second = service.embed_batch(["a", "bb", "ccc"])

    assert len(calls) == 2
    assert first[0][0] == 1.0 and first[2][0] == 3.0
    assert second.cached_count == 3
    assert second.require_all() == first


def test_retry_after_is_honored_for_rate_limit():
    attempts = 0
    delays = []

    def handler(request):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "1.5"})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2, 3]}]})

    service = _service(handler, max_retries=1, sleeper=delays.append)
    assert service.embed_one("query") == [1.0, 2.0, 3.0]
    assert attempts == 2
    assert delays == [1.5]


def test_dimension_mismatch_is_explicit_not_silently_cached():
    service = _service(
        lambda request: httpx.Response(
            200, json={"data": [{"index": 0, "embedding": [1, 2]}]}
        )
    )
    result = service.embed_batch(["bad"])
    assert len(result.failures) == 1
    assert result.failures[0].error_type == "EmbeddingDimensionError"
    with pytest.raises(Exception, match="dimension mismatch"):
        result.require_all()


def test_global_provider_failure_stops_after_first_batch():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={"code": "Arrearage", "message": "account is not in good standing"},
        )

    service = _service(handler)
    result = service.embed_batch(["a", "b", "c", "d", "e"])

    assert calls == 1
    assert len(result.failures) == 5
    assert all(item.error_type == "EmbeddingProviderUnavailableError" for item in result.failures)
    with pytest.raises(EmbeddingProviderUnavailableError, match="Arrearage"):
        result.require_all()


def test_health_check_uses_only_fixed_non_sensitive_text():
    captured = []

    def handler(request):
        payload = __import__("json").loads(request.content)
        captured.extend(payload["input"])
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2, 3]}]})

    service = _service(handler)
    service.check_health()

    assert captured == ["MedAgent embedding provider health check"]


def test_all_retryable_batch_failures_remain_transient_for_pipeline_retry():
    def handler(request):
        raise httpx.ReadError("SSL EOF", request=request)

    service = _service(handler, max_retries=0)
    result = service.embed_batch(["first", "second"])

    assert result.failures and all(item.retryable for item in result.failures)
    with pytest.raises(EmbeddingTransientError, match="SSL EOF"):
        result.require_all()


def test_model_and_version_are_part_of_cache_key():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2, 3]}]})

    service = _service(handler)
    service.embed_one("same")
    service.version = "test-v2"
    service.embed_one("same")
    assert calls == 2


def test_dashscope_v3_caps_sync_batches_and_sends_dimension_parameter():
    calls = []

    def handler(request):
        payload = __import__("json").loads(request.content)
        calls.append(payload)
        texts = payload["input"]["texts"]
        return httpx.Response(200, json={"output": {"embeddings": [
            {"text_index": index, "embedding": [1, 2, 3]}
            for index, _text in enumerate(texts)
        ]}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    service = EmbeddingService(
        client=client,
        api_key="test-key",
        api_base=(
            "https://dashscope.aliyuncs.com/api/v1/services/embeddings/"
            "text-embedding/text-embedding"
        ),
        model="text-embedding-v3",
        dimensions=3,
        version="test-v1",
        batch_size=32,
    )

    assert len(service.embed_batch([f"text-{index}" for index in range(21)]).require_all()) == 21
    assert [len(call["input"]["texts"]) for call in calls] == [10, 10, 1]
    assert all(call["parameters"]["dimension"] == 3 for call in calls)
