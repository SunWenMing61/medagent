"""Redis-backed cache for safe, context-free standard knowledge-base answers."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from redis import Redis

from app.core.config import settings


logger = logging.getLogger(__name__)
_PERSONAL_CONTEXT = re.compile(
    r"(?:我|本人|患者|家人|孩子|父亲|母亲|孕妇).{0,16}"
    r"(?:症状|诊断|检查|化验|用药|剂量|血压|血糖|体温|心率|疼痛|过敏|病史|怀孕|孕周)",
    re.I,
)
_PERSONAL_MEASUREMENT = re.compile(
    r"\b\d{1,4}(?:\.\d+)?\s*(?:mmHg|mmol/L|mg/dL|mg|μg|kg|cm|℃|bpm)\b",
    re.I,
)


@dataclass(slots=True)
class CacheReservation:
    eligible: bool
    reason: str
    key: str | None = None
    lock_key: str | None = None
    lock_token: str | None = None
    cached: dict[str, Any] | None = None
    lookup_latency_ms: float = 0.0


class StandardAnswerCacheService:
    prefix = "medagent:standard_answer:v1"

    def __init__(self, redis_client: Any | None = None) -> None:
        self._client = redis_client
        self._redis_checked = redis_client is not None
        self._local_metrics: dict[int, dict[str, float]] = {}

    def _redis(self):
        if self._client is None and not self._redis_checked:
            self._redis_checked = True
            try:
                client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
                client.ping()
                self._client = client
            except Exception:
                logger.exception("Standard-answer Redis cache is unavailable; continuing without cache")
        return self._client

    @staticmethod
    def normalize(question: str) -> str:
        normalized = unicodedata.normalize("NFKC", question).casefold()
        return " ".join(normalized.split()).strip(" ,，。.!！?？;；:")

    def eligibility(
        self,
        *,
        question: str,
        assistant_profile: str,
        existing_session_id: int | None,
        kb_ids: list[int],
    ) -> tuple[bool, str]:
        if not settings.STANDARD_ANSWER_CACHE_ENABLED:
            return False, "disabled"
        if assistant_profile != "general_qa":
            return False, "memory_profile"
        if existing_session_id is not None:
            return False, "multi_turn_session"
        normalized = self.normalize(question)
        if not kb_ids:
            return False, "no_knowledge_base"
        if len(normalized) < 2 or len(normalized) > settings.STANDARD_ANSWER_CACHE_MAX_QUESTION_CHARS:
            return False, "question_length"
        if _PERSONAL_CONTEXT.search(normalized) or _PERSONAL_MEASUREMENT.search(normalized):
            return False, "personal_medical_context"
        return True, "standard_question"

    def _cache_key(
        self,
        *,
        tenant_id: int,
        question: str,
        kb_ids: list[int],
        kb_revision: str,
        session_type: str,
    ) -> str:
        material = json.dumps({
            "tenant_id": int(tenant_id),
            "question": self.normalize(question),
            "kb_ids": sorted({int(item) for item in kb_ids}),
            "kb_revision": kb_revision,
            "session_type": session_type,
            "cache_version": settings.STANDARD_ANSWER_CACHE_VERSION,
            "models": [
                settings.LLM_MODEL, settings.DEFAULT_AGENT_MODEL,
                settings.TRIAGE_MODEL, settings.EVIDENCE_MODEL,
                settings.ANSWER_MODEL, settings.SAFETY_MODEL,
                settings.EMBEDDING_MODEL, settings.EMBEDDING_VERSION,
            ],
            "retrieval": [
                settings.RETRIEVAL_CANDIDATE_K, settings.RRF_K,
                settings.EVIDENCE_MAX_CHUNKS, settings.EVIDENCE_MAX_TOKENS,
            ],
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return f"{self.prefix}:{int(tenant_id)}:{digest}"

    def _metrics_key(self, tenant_id: int) -> str:
        return f"{self.prefix}:metrics:{int(tenant_id)}"

    def _incr(self, tenant_id: int, field: str, amount: float = 1.0) -> None:
        local = self._local_metrics.setdefault(int(tenant_id), {})
        local[field] = local.get(field, 0.0) + float(amount)
        client = self._redis()
        if client is None:
            return
        try:
            client.hincrbyfloat(self._metrics_key(tenant_id), field, float(amount))
        except Exception:
            logger.exception("Failed to update standard-answer cache metric")

    @staticmethod
    def _decode(raw: Any) -> dict[str, Any] | None:
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else None
        except (TypeError, ValueError):
            return None

    def lookup(
        self,
        *,
        tenant_id: int,
        question: str,
        assistant_profile: str,
        existing_session_id: int | None,
        kb_ids: list[int],
        kb_revision: str,
        session_type: str,
    ) -> CacheReservation:
        started = time.perf_counter()
        self._incr(tenant_id, "requests")
        eligible, reason = self.eligibility(
            question=question,
            assistant_profile=assistant_profile,
            existing_session_id=existing_session_id,
            kb_ids=kb_ids,
        )
        if not eligible:
            self._incr(tenant_id, f"bypass_{reason}")
            return CacheReservation(False, reason)
        self._incr(tenant_id, "eligible_requests")
        client = self._redis()
        if client is None:
            self._incr(tenant_id, "redis_unavailable")
            return CacheReservation(False, "redis_unavailable")

        key = self._cache_key(
            tenant_id=tenant_id, question=question, kb_ids=kb_ids,
            kb_revision=kb_revision, session_type=session_type,
        )
        try:
            cached = self._decode(client.get(key))
            if cached:
                return self._hit(tenant_id, key, cached, started, "hit")

            lock_key = f"{key}:lock"
            token = uuid4().hex
            acquired = bool(client.set(
                lock_key, token, nx=True,
                ex=max(5, settings.STANDARD_ANSWER_CACHE_LOCK_SECONDS),
            ))
            if not acquired:
                wait_seconds = max(0, settings.STANDARD_ANSWER_CACHE_WAIT_MS) / 1000
                deadline = time.perf_counter() + wait_seconds
                while time.perf_counter() < deadline:
                    time.sleep(min(0.05, max(0.0, deadline - time.perf_counter())))
                    cached = self._decode(client.get(key))
                    if cached:
                        self._incr(tenant_id, "stampede_wait_hits")
                        return self._hit(tenant_id, key, cached, started, "wait_hit")
                self._incr(tenant_id, "stampede_wait_timeouts")
                self._incr(tenant_id, "misses")
                return CacheReservation(True, "lock_busy", key=key, lookup_latency_ms=(time.perf_counter() - started) * 1000)

            self._incr(tenant_id, "misses")
            return CacheReservation(
                True, "miss", key=key, lock_key=lock_key, lock_token=token,
                lookup_latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception:
            self._incr(tenant_id, "errors")
            logger.exception("Standard-answer cache lookup failed")
            return CacheReservation(False, "cache_error")

    def _hit(self, tenant_id: int, key: str, cached: dict[str, Any], started: float, reason: str) -> CacheReservation:
        latency = (time.perf_counter() - started) * 1000
        self._incr(tenant_id, "hits")
        self._incr(tenant_id, "hit_latency_ms_total", latency)
        calls = max(1, int(cached.get("agent_call_count") or 1))
        self._incr(tenant_id, "model_calls_avoided", calls)
        saved = max(0.0, float(cached.get("generation_latency_ms") or 0.0) - latency)
        self._incr(tenant_id, "estimated_latency_saved_ms_total", saved)
        return CacheReservation(True, reason, key=key, cached=cached, lookup_latency_ms=latency)

    @staticmethod
    def cacheable_state(state: dict[str, Any]) -> tuple[bool, str]:
        if state.get("status") != "completed":
            return False, "not_completed"
        if state.get("evidence_status") != "sufficient" or not state.get("citations"):
            return False, "insufficient_evidence"
        if state.get("safety_status") != "pass" or state.get("risk_level") not in {None, "low"}:
            return False, "safety_not_passed"
        if state.get("errors") or state.get("need_clarification") or state.get("human_review_required"):
            return False, "non_reusable_state"
        if not str(state.get("final_answer") or "").strip():
            return False, "empty_answer"
        return True, "reusable"

    def store(
        self,
        reservation: CacheReservation,
        *,
        tenant_id: int,
        state: dict[str, Any],
        generation_latency_ms: float,
    ) -> bool:
        if not reservation.eligible or not reservation.key or not reservation.lock_token:
            return False
        reusable, reason = self.cacheable_state(state)
        if not reusable:
            self._incr(tenant_id, f"not_stored_{reason}")
            self.release(reservation)
            return False
        payload = {
            "final_answer": state.get("final_answer"),
            "citations": state.get("citations") or [],
            "safety_status": state.get("safety_status"),
            "risk_level": state.get("risk_level"),
            "evidence_status": state.get("evidence_status"),
            "agent_call_count": max(1, int(state.get("agent_call_count") or 1)),
            "tool_call_count": max(0, int(state.get("tool_call_count") or 0)),
            "answer_variants": state.get("answer_variants") or [],
            "recommended_variant_id": state.get("recommended_variant_id"),
            "generation_latency_ms": max(0.0, float(generation_latency_ms)),
            "cached_at": time.time(),
        }
        client = self._redis()
        if client is None:
            return False
        try:
            client.setex(
                reservation.key,
                max(60, settings.STANDARD_ANSWER_CACHE_TTL_SECONDS),
                json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str),
            )
            self._incr(tenant_id, "stores")
            self._incr(tenant_id, "model_calls_executed", payload["agent_call_count"])
            self._incr(tenant_id, "miss_generation_latency_ms_total", generation_latency_ms)
            return True
        except Exception:
            self._incr(tenant_id, "errors")
            logger.exception("Standard-answer cache store failed")
            return False
        finally:
            self.release(reservation)

    def release(self, reservation: CacheReservation) -> None:
        if not reservation.lock_key or not reservation.lock_token:
            return
        client = self._redis()
        if client is None:
            return
        try:
            client.eval(
                "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end",
                1, reservation.lock_key, reservation.lock_token,
            )
        except Exception:
            logger.exception("Failed to release standard-answer cache lock")

    def metrics(self, tenant_id: int) -> dict[str, Any]:
        values = dict(self._local_metrics.get(int(tenant_id), {}))
        client = self._redis()
        backend = "memory_fallback"
        if client is not None:
            try:
                raw = client.hgetall(self._metrics_key(tenant_id))
                values = {
                    (key.decode() if isinstance(key, bytes) else str(key)):
                    float(value.decode() if isinstance(value, bytes) else value)
                    for key, value in raw.items()
                }
                backend = "redis"
            except Exception:
                logger.exception("Failed to read standard-answer cache metrics")
        eligible = values.get("eligible_requests", 0.0)
        hits = values.get("hits", 0.0)
        stores = values.get("stores", 0.0)
        avoided = values.get("model_calls_avoided", 0.0)
        executed = values.get("model_calls_executed", 0.0)
        cold_avg = values.get("miss_generation_latency_ms_total", 0.0) / stores if stores else 0.0
        hit_avg = values.get("hit_latency_ms_total", 0.0) / hits if hits else 0.0
        return {
            "enabled": settings.STANDARD_ANSWER_CACHE_ENABLED,
            "backend": backend,
            "ttl_seconds": settings.STANDARD_ANSWER_CACHE_TTL_SECONDS,
            "requests": int(values.get("requests", 0)),
            "eligible_requests": int(eligible),
            "hits": int(hits),
            "misses": int(values.get("misses", 0)),
            "stores": int(stores),
            "hit_rate": hits / eligible if eligible else 0.0,
            "average_cold_latency_ms": cold_avg,
            "average_hit_latency_ms": hit_avg,
            "response_speed_improvement": max(0.0, 1 - hit_avg / cold_avg) if cold_avg and hits else 0.0,
            "model_calls_executed": int(executed),
            "model_calls_avoided": int(avoided),
            "estimated_model_call_reduction": avoided / (avoided + executed) if avoided + executed else 0.0,
            "estimated_latency_saved_ms": values.get("estimated_latency_saved_ms_total", 0.0),
            "stampede_wait_hits": int(values.get("stampede_wait_hits", 0)),
            "stampede_wait_timeouts": int(values.get("stampede_wait_timeouts", 0)),
            "raw": values,
        }


standard_answer_cache_service = StandardAnswerCacheService()
