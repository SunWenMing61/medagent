"""Reliable reusable client for batch embeddings."""

from __future__ import annotations

import hashlib
import logging
import random
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Callable, Sequence

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    """Base embedding failure."""


class EmbeddingTransientError(EmbeddingError):
    """Retryable provider/network failure."""


class EmbeddingResponseError(EmbeddingError):
    """Malformed or incomplete provider response."""


class EmbeddingDimensionError(EmbeddingResponseError):
    """Returned vectors do not match the configured dimensions."""


class EmbeddingProviderUnavailableError(EmbeddingError):
    """Global account/auth/quota failure; retrying each input cannot help."""


_FATAL_PROVIDER_CODES = {
    "Arrearage": "向量服务账户欠费或状态异常",
    "InvalidApiKey": "向量服务 API Key 无效",
    "InvalidAccessKey": "向量服务访问凭据无效",
    "AccessDenied": "向量服务拒绝访问",
    "Forbidden": "向量服务无访问权限",
    "QuotaExhausted": "向量服务配额已耗尽",
}


@dataclass(slots=True)
class EmbeddingFailure:
    index: int
    error_type: str
    message: str
    retryable: bool


@dataclass(slots=True)
class EmbeddingBatchResult:
    vectors: list[list[float] | None]
    failures: list[EmbeddingFailure] = field(default_factory=list)
    cached_count: int = 0

    def require_all(self) -> list[list[float]]:
        if self.failures:
            first = self.failures[0]
            if all(failure.error_type == "EmbeddingProviderUnavailableError" for failure in self.failures):
                error_type = EmbeddingProviderUnavailableError
            elif all(failure.retryable for failure in self.failures):
                error_type = EmbeddingTransientError
            else:
                error_type = EmbeddingError
            raise error_type(
                f"Embedding batch has {len(self.failures)} failed item(s); "
                f"first index={first.index}: {first.message}"
            )
        return [vector for vector in self.vectors if vector is not None]


class EmbeddingService:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        version: str | None = None,
        batch_size: int | None = None,
        max_retries: int | None = None,
        cache_max_entries: int | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.dimensions = dimensions
        self.version = version
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.cache_max_entries = cache_max_entries
        timeout = httpx.Timeout(settings.EMBEDDING_TIMEOUT_SECONDS, connect=10.0)
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._sleep = sleeper
        self._random = random_value
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.RLock()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def embed_one(self, text: str) -> list[float]:
        return self.embed_batch([text]).require_all()[0]

    def check_health(self) -> None:
        """Validate the provider without transmitting user or document text."""
        self._request_with_retry(["MedAgent embedding provider health check"])

    def embed_batch(
        self,
        texts: Sequence[str],
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> EmbeddingBatchResult:
        values = [str(text).strip() for text in texts]
        vectors: list[list[float] | None] = [None] * len(values)
        failures: list[EmbeddingFailure] = []
        missing: list[tuple[int, str, str]] = []
        cached_count = 0

        for index, text in enumerate(values):
            if not text:
                failures.append(EmbeddingFailure(index, "empty_input", "Text is empty", False))
                continue
            key = self._cache_key(text)
            cached = self._cache_get(key)
            if cached is not None:
                vectors[index] = cached
                cached_count += 1
            else:
                missing.append((index, text, key))

        size = max(1, self.batch_size or settings.EMBEDDING_BATCH_SIZE)
        api_url = (self.api_base or settings.EMBEDDING_API_BASE).lower()
        # DashScope text-embedding-v3/v4 accepts at most ten input strings in
        # one synchronous request.  A larger generic batch size is rejected
        # with HTTP 400, which used to trigger the whole PDF pipeline again.
        if "dashscope" in api_url and "/services/embeddings/" in api_url:
            size = min(size, 10)
        completed = cached_count + len(failures)
        for offset in range(0, len(missing), size):
            batch = missing[offset:offset + size]
            try:
                batch_vectors = self._request_with_retry([item[1] for item in batch])
                for (index, _text, key), vector in zip(batch, batch_vectors):
                    vectors[index] = vector
                    self._cache_put(key, vector)
            except EmbeddingError as exc:
                retryable = isinstance(exc, EmbeddingTransientError)
                failures.extend(
                    EmbeddingFailure(index, type(exc).__name__, str(exc), retryable)
                    for index, _text, _key in batch
                )
                if isinstance(exc, EmbeddingProviderUnavailableError):
                    remaining = missing[offset + len(batch):]
                    failures.extend(
                        EmbeddingFailure(index, type(exc).__name__, str(exc), False)
                        for index, _text, _key in remaining
                    )
                    completed += len(batch) + len(remaining)
                    if progress_callback:
                        progress_callback(completed, len(values))
                    break
            completed += len(batch)
            if progress_callback:
                progress_callback(completed, len(values))

        return EmbeddingBatchResult(vectors, failures, cached_count)

    def _request_with_retry(self, texts: list[str]) -> list[list[float]]:
        retries = max(0, self.max_retries if self.max_retries is not None else settings.EMBEDDING_MAX_RETRIES)
        for attempt in range(retries + 1):
            try:
                return self._request(texts)
            except EmbeddingTransientError as exc:
                if attempt >= retries:
                    raise
                retry_after = getattr(exc, "retry_after", None)
                delay = retry_after if retry_after is not None else min(8.0, 0.5 * (2 ** attempt))
                delay += self._random() * 0.25
                logger.warning(
                    "Embedding provider transient failure attempt=%d/%d delay=%.2fs: %s",
                    attempt + 1, retries + 1, delay, exc,
                )
                self._sleep(delay)
        raise AssertionError("unreachable")

    def _request(self, texts: list[str]) -> list[list[float]]:
        api_key = self.api_key if self.api_key is not None else settings.EMBEDDING_API_KEY
        if not api_key:
            raise EmbeddingResponseError("EMBEDDING_API_KEY is not configured")
        url = (self.api_base or settings.EMBEDDING_API_BASE).rstrip("/")
        model = self.model or settings.EMBEDDING_MODEL
        dimensions = self.dimensions or settings.EMBEDDING_DIMENSIONS
        payload: dict = {"model": model}
        if "dashscope" in url:
            payload["input"] = {"texts": texts}
            payload["parameters"] = {"dimension": dimensions}
        else:
            payload["input"] = texts
            payload["dimensions"] = dimensions
        request_hash = hashlib.sha256("\x1f".join(texts).encode("utf-8")).hexdigest()
        try:
            response = self._client.post(
                url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Idempotency-Key": f"embed-{request_hash}",
                },
                json=payload,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise EmbeddingTransientError(f"Embedding network failure: {exc}") from exc

        if response.status_code == 429 or response.status_code >= 500:
            error = EmbeddingTransientError(f"Embedding provider returned HTTP {response.status_code}")
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    error.retry_after = min(float(retry_after), 30.0)  # type: ignore[attr-defined]
                except ValueError:
                    pass
            raise error
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            provider_code = str(data.get("code") or "").strip()
            safe_reason = _FATAL_PROVIDER_CODES.get(provider_code)
            if safe_reason:
                raise EmbeddingProviderUnavailableError(f"{safe_reason}（{provider_code}）")
            detail = f"，code={provider_code}" if provider_code else ""
            raise EmbeddingResponseError(
                f"Embedding provider rejected request: HTTP {response.status_code}{detail}"
            )
        if not data:
            raise EmbeddingResponseError("Embedding provider returned invalid JSON")

        if isinstance(data.get("output"), dict) and isinstance(data["output"].get("embeddings"), list):
            raw = data["output"]["embeddings"]
        elif isinstance(data.get("data"), list):
            raw = sorted(data["data"], key=lambda item: item.get("index", 0))
        else:
            raise EmbeddingResponseError("Embedding response has no embeddings array")
        if len(raw) != len(texts):
            raise EmbeddingResponseError(
                f"Embedding response count mismatch: expected {len(texts)}, got {len(raw)}"
            )

        vectors: list[list[float]] = []
        for item in raw:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not all(isinstance(value, (int, float)) for value in vector):
                raise EmbeddingResponseError("Embedding response contains a non-numeric vector")
            if len(vector) != dimensions:
                raise EmbeddingDimensionError(
                    f"Embedding dimension mismatch: configured {dimensions}, got {len(vector)}"
                )
            vectors.append([float(value) for value in vector])
        return vectors

    def _cache_key(self, text: str) -> str:
        model = self.model or settings.EMBEDDING_MODEL
        dimensions = self.dimensions or settings.EMBEDDING_DIMENSIONS
        version = self.version or settings.EMBEDDING_VERSION
        return hashlib.sha256(
            "\x1f".join([model, str(dimensions), version, text]).encode("utf-8")
        ).hexdigest()

    def _cache_get(self, key: str) -> list[float] | None:
        with self._lock:
            vector = self._cache.get(key)
            if vector is not None:
                self._cache.move_to_end(key)
                return vector.copy()
        return None

    def _cache_put(self, key: str, vector: list[float]) -> None:
        maximum = max(1, self.cache_max_entries or settings.EMBEDDING_CACHE_MAX_ENTRIES)
        with self._lock:
            self._cache[key] = vector.copy()
            self._cache.move_to_end(key)
            while len(self._cache) > maximum:
                self._cache.popitem(last=False)


embedding_service = EmbeddingService()
