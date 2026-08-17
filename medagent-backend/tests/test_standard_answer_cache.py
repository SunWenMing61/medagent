import json

from app.services.standard_answer_cache_service import StandardAnswerCacheService


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}

    def ping(self):
        return True

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, nx=False, ex=None):
        del ex
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def setex(self, key, ttl, value):
        assert ttl > 0
        self.values[key] = value
        return True

    def hincrbyfloat(self, key, field, amount):
        bucket = self.hashes.setdefault(key, {})
        bucket[field] = float(bucket.get(field, 0)) + float(amount)
        return bucket[field]

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def eval(self, script, key_count, key, token):
        del script, key_count
        if self.values.get(key) == token:
            del self.values[key]
            return 1
        return 0


def _state():
    return {
        "status": "completed",
        "evidence_status": "sufficient",
        "citations": [{"evidence_id": "ev_123"}],
        "safety_status": "pass",
        "risk_level": "low",
        "errors": [],
        "need_clarification": False,
        "human_review_required": False,
        "final_answer": "糖尿病是一组以高血糖为特征的代谢性疾病。",
        "agent_call_count": 4,
        "tool_call_count": 1,
    }


def _lookup(service, *, revision="rev-1", question="什么是糖尿病"):
    return service.lookup(
        tenant_id=1,
        question=question,
        assistant_profile="general_qa",
        existing_session_id=None,
        kb_ids=[2, 1],
        kb_revision=revision,
        session_type="qa",
    )


def test_standard_answer_is_cached_and_avoids_agent_calls():
    service = StandardAnswerCacheService(FakeRedis())
    first = _lookup(service)
    assert first.eligible and first.cached is None and first.lock_token
    assert service.store(first, tenant_id=1, state=_state(), generation_latency_ms=1000)

    second = _lookup(service)
    assert second.cached["final_answer"].startswith("糖尿病")
    metrics = service.metrics(1)
    assert metrics["hits"] == 1
    assert metrics["stores"] == 1
    assert metrics["model_calls_avoided"] == 4
    assert metrics["estimated_model_call_reduction"] == 0.5
    assert metrics["response_speed_improvement"] > 0.9


def test_memory_and_personal_medical_queries_bypass_cache():
    service = StandardAnswerCacheService(FakeRedis())
    memory = service.lookup(
        tenant_id=1, question="什么是糖尿病", assistant_profile="memory_qa",
        existing_session_id=None, kb_ids=[1], kb_revision="v1", session_type="qa",
    )
    personal = _lookup(service, question="我检查血糖是 12 mmol/L，该吃什么药")
    assert not memory.eligible and memory.reason == "memory_profile"
    assert not personal.eligible and personal.reason == "personal_medical_context"


def test_document_revision_invalidates_old_answer():
    redis = FakeRedis()
    service = StandardAnswerCacheService(redis)
    first = _lookup(service, revision="rev-1")
    service.store(first, tenant_id=1, state=_state(), generation_latency_ms=500)
    changed = _lookup(service, revision="rev-2")
    assert changed.cached is None
    assert changed.key != first.key


def test_unsafe_or_insufficient_answers_are_not_stored():
    service = StandardAnswerCacheService(FakeRedis())
    reservation = _lookup(service)
    state = _state()
    state["safety_status"] = "blocked"
    assert service.store(reservation, tenant_id=1, state=state, generation_latency_ms=500) is False
    assert _lookup(service).cached is None
