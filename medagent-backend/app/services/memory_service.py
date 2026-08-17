"""Layered, namespace-first Agent Memory with policy, conflict, TTL and audit."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.chunking.token_counter import count_tokens
from app.core.config import settings
from app.models.memory import (
    AgentEpisode, AgentMemory, AgentMemoryAudit, AgentProcedure,
    MemoryRetrievalTrace, UserMemorySetting,
)
from app.schemas.memory import (
    ActiveEntity, EpisodicMemory, MemoryAccessPolicy, MemoryAuditResponse,
    MemoryCandidate, MemoryPolicyDecision, ProceduralMemory, RetrievedMemory,
    SemanticMemoryResponse, SessionMemory, UnresolvedQuestion,
)
from app.services.session_memory_repository import (
    MongoSessionMemoryRepository,
    SessionMemoryRepository,
    SqlSessionMemoryRepository,
)


_TOKEN = re.compile(r"[A-Za-z0-9μ₂⁹⁺]+(?:[./-][A-Za-z0-9μ₂⁹⁺]+)*|[\u4e00-\u9fff]{1,8}", re.I)
_INJECTION = re.compile(r"ignore (?:all|previous)|system prompt|developer message|忽略(?:以上|之前)|泄露.*提示词|调用.*工具", re.I)
_MEDICAL_INFERENCE = re.compile(r"可能(?:患有|得了)|疑似|诊断为|probably have|likely diagnosis", re.I)
_PERSISTENT_PREFERENCE = re.compile(
    r"请记住|记住我的|以后(?:请|不要|别|都)|今后(?:请|不要|别|都)|"
    r"我(?:更)?偏好|我更喜欢|please remember|from now on|i prefer",
    re.I,
)
logger = logging.getLogger(__name__)


def memory_namespace(tenant_id: int, user_id: int | None, memory_type: str, agent_name: str | None = None) -> str:
    owner = f"user:{int(user_id)}" if user_id is not None else f"agent:{agent_name or 'shared'}"
    return f"tenant:{int(tenant_id)}/{owner}/memory_type:{memory_type}"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _trust(source_type: str) -> str:
    return "high" if source_type in {"user_explicit", "user_confirmed", "admin_import"} else ("medium" if source_type == "system_observed" else "low")


def _tokens(value: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(value or "")}


class MemoryCipher:
    def __init__(self) -> None:
        configured = getattr(settings, "MEMORY_ENCRYPTION_KEY", None)
        if configured:
            key = configured.encode("utf-8")
        else:
            digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
            key = base64.urlsafe_b64encode(digest)
        self._fernet = Fernet(key)

    def protect(self, value: str | dict, sensitivity: str) -> tuple[Any, str]:
        if sensitivity not in {"medical_sensitive", "highly_sensitive"}:
            return value, self.searchable(value)
        token = self._fernet.encrypt(json.dumps(value, ensure_ascii=False).encode("utf-8")).decode("ascii")
        return {"encrypted": token, "algorithm": "fernet-v1"}, "[sensitive-memory]"

    def reveal(self, value: Any) -> Any:
        if not isinstance(value, dict) or "encrypted" not in value:
            return value
        try:
            return json.loads(self._fernet.decrypt(value["encrypted"].encode("ascii")).decode("utf-8"))
        except (InvalidToken, ValueError, TypeError):
            return "[unavailable encrypted memory]"

    @staticmethod
    def searchable(value: str | dict) -> str:
        return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True)


class MemoryPolicyService:
    _policies = {
        "supervisor": ({"session", "semantic", "episodic", "procedural"}, {"session", "episodic"}),
        "input_safety": ({"session", "procedural"}, set()),
        "input_triage": ({"session", "semantic", "procedural"}, set()),
        "query_understanding": ({"session", "semantic", "episodic", "procedural"}, set()),
        "retrieval": ({"session", "semantic", "episodic", "procedural"}, set()),
        "evidence_verification": ({"session", "episodic", "procedural"}, set()),
        "answer_generation": ({"session", "semantic", "procedural"}, set()),
        "output_safety": ({"session", "episodic", "procedural"}, {"episodic"}),
        "user_control": ({"session", "semantic", "episodic"}, {"semantic", "session"}),
        "admin": ({"session", "semantic", "episodic", "procedural"}, {"semantic", "episodic", "procedural"}),
    }

    def access_policy(self, agent_name: str) -> MemoryAccessPolicy:
        readable, writable = self._policies.get(agent_name, (set(), set()))
        return MemoryAccessPolicy(
            agent_name=agent_name,
            readable_memory_types=readable,
            writable_memory_types=writable,
            max_items=settings.MEMORY_MAX_ITEMS_PER_AGENT,
            max_tokens=settings.MEMORY_MAX_TOKENS_PER_AGENT,
            allowed_sensitivity={"normal", "personal"} | ({"medical_sensitive"} if settings.MEMORY_MEDICAL_SENSITIVE_ENABLED else set()),
        )

    def decide_write(
        self, candidate: MemoryCandidate, *, agent_name: str, long_term_enabled: bool,
        medical_sensitive_enabled: bool = False,
    ) -> MemoryPolicyDecision:
        policy = self.access_policy(agent_name)
        if not settings.MEMORY_ENABLED or not settings.LONG_TERM_MEMORY_ENABLED or not long_term_enabled:
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Long-term memory is disabled.")
        if candidate.memory_type not in policy.writable_memory_types:
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Agent is not allowed to write this memory type.")
        if candidate.source_role == "assistant" or candidate.source_type in {"model_inferred", "external_retrieval"}:
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Assistant, inferred, and retrieved facts cannot become user fact memory.")
        text = MemoryCipher.searchable(candidate.value)
        if _INJECTION.search(text):
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Prompt-control text is not eligible for memory.")
        if candidate.sensitivity == "highly_sensitive":
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Highly sensitive content is never auto-stored.")
        if candidate.sensitivity == "medical_sensitive" and not (
            settings.MEMORY_MEDICAL_SENSITIVE_ENABLED and medical_sensitive_enabled
        ):
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Medical-sensitive long-term memory is disabled.")
        if candidate.sensitivity not in policy.allowed_sensitivity:
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Sensitivity is outside the agent policy.")
        if _MEDICAL_INFERENCE.search(text) and not candidate.confirmed:
            return MemoryPolicyDecision(allowed=False, status="reject", reason="Unconfirmed medical inference is not memory.")
        if not (candidate.explicit_instruction or candidate.confirmed or candidate.source_type == "admin_import"):
            return MemoryPolicyDecision(allowed=False, status="needs_confirmation", reason="Long-term memory requires explicit user intent or confirmation.")
        return MemoryPolicyDecision(allowed=True, status="accept", reason="Explicit/confirmed user memory passed policy.")


class AgentMemoryService:
    def __init__(self) -> None:
        self.policy = MemoryPolicyService()
        self.cipher = MemoryCipher()

    @staticmethod
    def _setting(db: Session, tenant_id: int, user_id: int) -> UserMemorySetting:
        row = db.query(UserMemorySetting).filter_by(tenant_id=tenant_id, user_id=user_id).first()
        if not row:
            row = UserMemorySetting(tenant_id=tenant_id, user_id=user_id, long_term_enabled=True, medical_sensitive_enabled=False)
            db.add(row)
            db.flush()
        return row

    def write_candidate(
        self, db: Session, *, tenant_id: int, user_id: int, candidate: MemoryCandidate,
        agent_name: str = "user_control", operator_type: str = "user", operator_id: str | None = None,
    ) -> tuple[SemanticMemoryResponse | None, MemoryPolicyDecision]:
        setting = self._setting(db, tenant_id, user_id)
        decision = self.policy.decide_write(
            candidate, agent_name=agent_name, long_term_enabled=bool(setting.long_term_enabled),
            medical_sensitive_enabled=bool(setting.medical_sensitive_enabled),
        )
        if not decision.allowed:
            self._audit(db, None, tenant_id, user_id, "reject", operator_type, operator_id, None, candidate.model_dump(mode="json"), decision.reason)
            return None, decision

        namespace = memory_namespace(tenant_id, user_id, "semantic")
        existing = db.query(AgentMemory).filter(
            AgentMemory.tenant_id == tenant_id,
            AgentMemory.user_id == user_id,
            AgentMemory.namespace == namespace,
            AgentMemory.memory_type == "semantic",
            AgentMemory.subject == candidate.subject,
            AgentMemory.predicate == candidate.predicate,
            AgentMemory.status == "active",
        ).order_by(AgentMemory.version.desc()).first()
        protected, searchable = self.cipher.protect(candidate.value, candidate.sensitivity)
        now = _now()
        if existing and self.cipher.reveal(existing.value_json) == candidate.value:
            before = self._snapshot(existing)
            existing.source_message_ids_json = list(dict.fromkeys((existing.source_message_ids_json or []) + candidate.source_message_ids))
            existing.confidence = max(existing.confidence, candidate.confidence)
            existing.importance = max(existing.importance, candidate.importance)
            self._audit(db, existing.id, tenant_id, user_id, "update", operator_type, operator_id, before, self._snapshot(existing), "Duplicate fact merged with additional provenance.")
            db.flush()
            return self._response(existing), decision

        status = "active"
        version = 1
        if existing:
            version = int(existing.version) + 1
            if candidate.source_type in {"user_explicit", "user_confirmed", "admin_import"}:
                before = self._snapshot(existing)
                existing.status = "superseded"
                existing.valid_to = now
                self._audit(db, existing.id, tenant_id, user_id, "supersede", operator_type, operator_id, before, self._snapshot(existing), "Explicit newer value superseded the active version.")
            else:
                status = "disputed"

        expires = candidate.expires_at.replace(tzinfo=None) if candidate.expires_at else now + timedelta(days=settings.MEMORY_DEFAULT_TTL_DAYS)
        row = AgentMemory(
            id=f"mem_{uuid4().hex}", tenant_id=tenant_id, user_id=user_id,
            namespace=namespace, memory_type="semantic", category=candidate.category,
            subject=candidate.subject, predicate=candidate.predicate, value_json=protected,
            searchable_text=searchable[:4000], source_type=candidate.source_type,
            source_message_ids_json=candidate.source_message_ids, confidence=candidate.confidence,
            importance=candidate.importance, sensitivity=candidate.sensitivity,
            trust_level=_trust(candidate.source_type), status=status, valid_from=now,
            expires_at=expires, version=version, can_support_medical_claim=False,
        )
        db.add(row)
        db.flush()
        operation = "dispute" if status == "disputed" else "create"
        self._audit(db, row.id, tenant_id, user_id, operation, operator_type, operator_id, None, self._snapshot(row), decision.reason)
        return self._response(row), decision

    def retrieve(
        self, db: Session, *, tenant_id: int, user_id: int, query: str, agent_name: str,
        memory_types: set[str] | None = None, request_id: str = "memory-query",
    ) -> tuple[list[RetrievedMemory], int]:
        started = time.perf_counter()
        policy = self.policy.access_policy(agent_name)
        setting = self._setting(db, tenant_id, user_id)
        requested = (memory_types or {"semantic"}) & set(policy.readable_memory_types)
        if "semantic" not in requested or not settings.MEMORY_ENABLED or not setting.long_term_enabled:
            return [], 0
        allowed_sensitivity = set(policy.allowed_sensitivity)
        if not setting.medical_sensitive_enabled:
            allowed_sensitivity.discard("medical_sensitive")
        namespace = memory_namespace(tenant_id, user_id, "semantic")
        now = _now()
        # Namespace, owner, type, status, TTL and sensitivity are filtered in SQL before scoring.
        rows = db.query(AgentMemory).filter(
            AgentMemory.tenant_id == tenant_id,
            AgentMemory.user_id == user_id,
            AgentMemory.namespace == namespace,
            AgentMemory.memory_type == "semantic",
            AgentMemory.status == "active",
            AgentMemory.sensitivity.in_(sorted(allowed_sensitivity)),
            or_(AgentMemory.expires_at.is_(None), AgentMemory.expires_at > now),
        ).order_by(AgentMemory.importance.desc(), AgentMemory.updated_at.desc()).limit(200).all()
        query_tokens = _tokens(query)
        scored: list[RetrievedMemory] = []
        for row in rows:
            candidate_tokens = _tokens(f"{row.subject} {row.predicate} {row.searchable_text}")
            query_overlap = len(query_tokens & candidate_tokens) / max(len(query_tokens | candidate_tokens), 1)
            task = len(query_tokens & _tokens(f"{row.subject} {row.predicate}")) / max(len(query_tokens), 1)
            age_days = max(0.0, (now - (row.updated_at or row.created_at or now)).total_seconds() / 86400)
            recency = math.pow(0.5, age_days / max(settings.MEMORY_RECENCY_HALF_LIFE_DAYS, 1))
            score = (
                settings.MEMORY_WEIGHT_QUERY_OVERLAP * query_overlap
                + settings.MEMORY_WEIGHT_TASK * task
                + settings.MEMORY_WEIGHT_IMPORTANCE * float(row.importance)
                + settings.MEMORY_WEIGHT_RECENCY * recency
                + settings.MEMORY_WEIGHT_CONFIDENCE * float(row.confidence)
            )
            reasons = []
            if query_overlap:
                reasons.append("query_overlap")
            if task:
                reasons.append("subject_predicate_match")
            scored.append(RetrievedMemory(**self._response(row).model_dump(), final_score=min(1.0, score), match_reasons=reasons))
        scored.sort(key=lambda item: (-item.final_score, -item.importance, -(item.updated_at or now).timestamp()))
        selected: list[RetrievedMemory] = []
        token_total = 0
        for item in scored:
            tokens = count_tokens(f"{item.subject} {item.predicate} {item.value}")
            if selected and token_total + tokens > policy.max_tokens:
                continue
            selected.append(item)
            token_total += tokens
            if len(selected) >= policy.max_items:
                break
        latency = round((time.perf_counter() - started) * 1000, 3)
        db.add(MemoryRetrievalTrace(
            id=f"mrt_{uuid4().hex}", request_id=request_id, tenant_id=tenant_id, user_id=user_id,
            agent_name=agent_name, memory_types_json=sorted(requested),
            query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest(), candidate_count=len(rows),
            selected_count=len(selected), memory_tokens=token_total, latency_ms=latency,
        ))
        db.flush()
        return selected, token_total

    def list_memories(self, db: Session, *, tenant_id: int, user_id: int, include_inactive: bool = False) -> list[SemanticMemoryResponse]:
        query = db.query(AgentMemory).filter(AgentMemory.tenant_id == tenant_id, AgentMemory.user_id == user_id)
        if not include_inactive:
            query = query.filter(AgentMemory.status.in_(["active", "disputed"]))
        return [self._response(row) for row in query.order_by(AgentMemory.updated_at.desc()).all()]

    def update_memory(self, db: Session, *, memory_id: str, tenant_id: int, user_id: int, value: Any, sensitivity: str | None, expires_at: datetime | None, reason: str) -> SemanticMemoryResponse:
        row = self._owned(db, memory_id, tenant_id, user_id)
        prior_value = self.cipher.reveal(row.value_json)
        candidate = MemoryCandidate(
            category=row.category, subject=row.subject, predicate=row.predicate, value=value,
            source_message_ids=row.source_message_ids_json or [], confidence=1.0,
            importance=row.importance, reason_to_remember=reason,
            sensitivity=sensitivity or row.sensitivity, source_type="user_explicit",
            source_role="user", explicit_instruction=True, confirmed=True, expires_at=expires_at,
        )
        result, decision = self.write_candidate(db, tenant_id=tenant_id, user_id=user_id, candidate=candidate, operator_id=str(user_id))
        if not result or not decision.allowed:
            raise ValueError(decision.reason)
        self._audit(db, result.memory_id, tenant_id, user_id, "update", "user", str(user_id), {"value": prior_value}, {"value": value}, reason)
        return result

    def delete_memory(self, db: Session, *, memory_id: str, tenant_id: int, user_id: int, reason: str = "user deletion") -> None:
        row = self._owned(db, memory_id, tenant_id, user_id)
        before = self._snapshot(row)
        row.status = "deleted"
        row.valid_to = _now()
        row.searchable_text = "[deleted]"
        self._audit(db, row.id, tenant_id, user_id, "delete", "user", str(user_id), before, self._snapshot(row), reason)

    def learn_preferences_from_message(
        self,
        db: Session,
        *,
        tenant_id: int,
        user_id: int,
        text: str,
        source_message_id: str,
    ) -> SemanticMemoryResponse | None:
        """Persist only explicit, durable user preferences; never persist the full chat."""
        normalized = re.sub(r"\s+", " ", (text or "").strip())
        if not normalized or not _PERSISTENT_PREFERENCE.search(normalized):
            return None
        lowered = normalized.lower()
        if re.search(r"中文|英文|汉语|英语|chinese|english", lowered):
            predicate = "answer_language"
        elif re.search(r"简洁|精简|详细|展开|concise|brief|detailed", lowered):
            predicate = "answer_detail_level"
        elif re.search(r"表格|分点|列表|markdown|table|bullet", lowered):
            predicate = "answer_format"
        elif re.search(r"专业|通俗|语气|口吻|professional|plain language|tone", lowered):
            predicate = "answer_tone"
        else:
            predicate = "general_preference"
        candidate = MemoryCandidate(
            memory_type="semantic",
            category="communication_style" if predicate.startswith("answer_") else "preference",
            subject="user",
            predicate=predicate,
            value=normalized[:500],
            source_message_ids=[source_message_id],
            confidence=1.0,
            importance=0.8,
            reason_to_remember="Explicit durable preference stated by the user",
            sensitivity="normal",
            source_type="user_explicit",
            source_role="user",
            explicit_instruction=True,
            confirmed=True,
        )
        result, decision = self.write_candidate(
            db,
            tenant_id=tenant_id,
            user_id=user_id,
            candidate=candidate,
            agent_name="user_control",
            operator_type="user",
            operator_id=str(user_id),
        )
        return result if decision.allowed else None

    def clear(self, db: Session, *, tenant_id: int, user_id: int) -> int:
        rows = db.query(AgentMemory).filter(AgentMemory.tenant_id == tenant_id, AgentMemory.user_id == user_id, AgentMemory.status.in_(["active", "disputed"])).all()
        for row in rows:
            self.delete_memory(db, memory_id=row.id, tenant_id=tenant_id, user_id=user_id, reason="user cleared long-term memory")
        return len(rows)

    def set_enabled(self, db: Session, *, tenant_id: int, user_id: int, enabled: bool) -> None:
        setting = self._setting(db, tenant_id, user_id)
        setting.long_term_enabled = enabled

    def settings(self, db: Session, *, tenant_id: int, user_id: int) -> dict[str, bool]:
        row = self._setting(db, tenant_id, user_id)
        return {
            "long_term_memory_enabled": bool(row.long_term_enabled),
            "medical_sensitive_memory_enabled": bool(row.medical_sensitive_enabled),
        }

    def set_medical_sensitive(self, db: Session, *, tenant_id: int, user_id: int, enabled: bool) -> None:
        row = self._setting(db, tenant_id, user_id)
        row.medical_sensitive_enabled = enabled

    def audit(self, db: Session, *, tenant_id: int, user_id: int, limit: int = 100) -> list[MemoryAuditResponse]:
        rows = db.query(AgentMemoryAudit).filter_by(tenant_id=tenant_id, user_id=user_id).order_by(AgentMemoryAudit.created_at.desc()).limit(min(max(limit, 1), 500)).all()
        return [MemoryAuditResponse(
            audit_id=row.id, memory_id=row.memory_id, operation=row.operation,
            operator_type=row.operator_type, reason=row.reason,
            before_value=row.before_value_json, after_value=row.after_value_json, created_at=row.created_at,
        ) for row in rows]

    def expire(self, db: Session, *, now: datetime | None = None) -> int:
        current = (now or _now()).replace(tzinfo=None)
        rows = db.query(AgentMemory).filter(AgentMemory.status.in_(["active", "disputed"]), AgentMemory.expires_at.isnot(None), AgentMemory.expires_at <= current).all()
        for row in rows:
            before = self._snapshot(row)
            row.status = "expired"
            row.valid_to = current
            self._audit(db, row.id, row.tenant_id, row.user_id, "expire", "system", "memory-expirer", before, self._snapshot(row), "TTL elapsed")
        return len(rows)

    def record_episode(
        self, db: Session, *, tenant_id: int, user_id: int | None, thread_id: str | None,
        request_id: str | None, event_type: str, task_type: str, situation_summary: str,
        action_summary: str, outcome_summary: str, success: bool,
        quality_score: float | None = None, related_entities: list[str] | None = None,
        source_run_ids: list[str] | None = None, reusable: bool = False,
        expires_at: datetime | None = None, agent_name: str = "supervisor",
    ) -> EpisodicMemory:
        if "episodic" not in self.policy.access_policy(agent_name).writable_memory_types:
            raise PermissionError("Agent cannot write episodic memory")
        row = AgentEpisode(
            id=f"epi_{uuid4().hex}", tenant_id=tenant_id, user_id=user_id,
            thread_id=thread_id, request_id=request_id, event_type=event_type,
            task_type=task_type, situation_summary=situation_summary[:4000],
            action_summary=action_summary[:4000], outcome_summary=outcome_summary[:4000],
            success=success, quality_score=quality_score,
            related_entities_json=related_entities or [], source_run_ids_json=source_run_ids or [],
            reusable=bool(reusable),
            expires_at=(expires_at or (_now() + timedelta(days=30))).replace(tzinfo=None),
        )
        db.add(row)
        db.flush()
        return self._episode_response(row)

    def retrieve_episodes(
        self, db: Session, *, tenant_id: int, user_id: int | None, query: str,
        agent_name: str, task_type: str | None = None, limit: int = 3,
    ) -> list[EpisodicMemory]:
        if "episodic" not in self.policy.access_policy(agent_name).readable_memory_types:
            return []
        now = _now()
        statement = db.query(AgentEpisode).filter(
            AgentEpisode.tenant_id == tenant_id,
            or_(AgentEpisode.user_id == user_id, AgentEpisode.user_id.is_(None)),
            AgentEpisode.reusable.is_(True),
            or_(AgentEpisode.expires_at.is_(None), AgentEpisode.expires_at > now),
        )
        if task_type:
            statement = statement.filter(AgentEpisode.task_type == task_type)
        candidates = statement.order_by(AgentEpisode.quality_score.desc(), AgentEpisode.created_at.desc()).limit(50).all()
        terms = _tokens(query)
        candidates.sort(key=lambda row: -len(terms & _tokens(f"{row.situation_summary} {row.outcome_summary} {' '.join(row.related_entities_json or [])}")))
        return [self._episode_response(row) for row in candidates[: max(1, min(limit, 3))]]

    def save_procedure(
        self, db: Session, *, tenant_id: int | None, scope: str, agent_name: str | None,
        task_type: str, trigger_conditions: dict, recommended_steps: list[str],
        prohibited_actions: list[str], required_tools: list[str], fallback_strategy: list[str],
        source: str, evaluation_score: float | None, version: str, status: str,
        approved_by: int | None,
    ) -> ProceduralMemory:
        if status == "active" and not (
            source == "developer_defined"
            or approved_by is not None
            or (source == "evaluation_derived" and evaluation_score is not None and evaluation_score >= 0.8)
        ):
            raise ValueError("Procedural memory can be activated only by developer definition, evaluation gate, or human approval")
        row = AgentProcedure(
            id=f"proc_{uuid4().hex}", tenant_id=tenant_id, scope=scope,
            agent_name=agent_name, task_type=task_type,
            trigger_conditions_json=trigger_conditions, recommended_steps_json=recommended_steps,
            prohibited_actions_json=prohibited_actions, required_tools_json=required_tools,
            fallback_strategy_json=fallback_strategy, source=source,
            evaluation_score=evaluation_score, version=version, status=status, approved_by=approved_by,
        )
        db.add(row)
        db.flush()
        return self._procedure_response(row)

    def retrieve_procedures(
        self, db: Session, *, tenant_id: int, agent_name: str, task_type: str,
        limit: int = 3,
    ) -> list[ProceduralMemory]:
        if "procedural" not in self.policy.access_policy(agent_name).readable_memory_types:
            return []
        rows = db.query(AgentProcedure).filter(
            AgentProcedure.status == "active",
            AgentProcedure.task_type == task_type,
            or_(AgentProcedure.tenant_id.is_(None), AgentProcedure.tenant_id == tenant_id),
            or_(AgentProcedure.agent_name.is_(None), AgentProcedure.agent_name == agent_name),
        ).order_by(AgentProcedure.evaluation_score.desc(), AgentProcedure.updated_at.desc()).limit(max(1, min(limit, 3))).all()
        return [self._procedure_response(row) for row in rows]

    def _owned(self, db: Session, memory_id: str, tenant_id: int, user_id: int) -> AgentMemory:
        row = db.query(AgentMemory).filter_by(id=memory_id, tenant_id=tenant_id, user_id=user_id).first()
        if not row:
            raise LookupError("Memory not found")
        return row

    def _response(self, row: AgentMemory) -> SemanticMemoryResponse:
        return SemanticMemoryResponse(
            memory_id=row.id, tenant_id=row.tenant_id, user_id=row.user_id,
            namespace=row.namespace, memory_type=row.memory_type, category=row.category,
            subject=row.subject, predicate=row.predicate, value=self.cipher.reveal(row.value_json),
            source_type=row.source_type, source_message_ids=row.source_message_ids_json or [],
            confidence=row.confidence, importance=row.importance, sensitivity=row.sensitivity,
            trust_level=row.trust_level, status=row.status, valid_from=row.valid_from,
            valid_to=row.valid_to, expires_at=row.expires_at, version=row.version,
            can_support_medical_claim=False, created_at=row.created_at, updated_at=row.updated_at,
        )

    @staticmethod
    def _snapshot(row: AgentMemory) -> dict[str, Any]:
        value = "[encrypted]" if row.sensitivity in {"medical_sensitive", "highly_sensitive"} else row.value_json
        return {"id": row.id, "status": row.status, "version": row.version, "value": value, "sensitivity": row.sensitivity}

    @staticmethod
    def _audit(db: Session, memory_id: str | None, tenant_id: int, user_id: int | None, operation: str, operator_type: str, operator_id: str | None, before: dict | None, after: dict | None, reason: str) -> None:
        db.add(AgentMemoryAudit(
            id=f"ma_{uuid4().hex}", memory_id=memory_id, tenant_id=tenant_id, user_id=user_id,
            operation=operation, operator_type=operator_type, operator_id=operator_id,
            before_value_json=before, after_value_json=after, reason=reason[:2000],
        ))

    @staticmethod
    def _episode_response(row: AgentEpisode) -> EpisodicMemory:
        return EpisodicMemory(
            episode_id=row.id, tenant_id=row.tenant_id, user_id=row.user_id,
            thread_id=row.thread_id, request_id=row.request_id, event_type=row.event_type,
            task_type=row.task_type, situation_summary=row.situation_summary,
            action_summary=row.action_summary, outcome_summary=row.outcome_summary,
            success=row.success, quality_score=row.quality_score,
            related_entities=row.related_entities_json or [], source_run_ids=row.source_run_ids_json or [],
            reusable=row.reusable, expires_at=row.expires_at,
            created_at=row.created_at or _now(),
        )

    @staticmethod
    def _procedure_response(row: AgentProcedure) -> ProceduralMemory:
        return ProceduralMemory(
            procedure_id=row.id, scope=row.scope, agent_name=row.agent_name,
            task_type=row.task_type, trigger_conditions=row.trigger_conditions_json or {},
            recommended_steps=row.recommended_steps_json or [],
            prohibited_actions=row.prohibited_actions_json or [], required_tools=row.required_tools_json or [],
            fallback_strategy=row.fallback_strategy_json or [], source=row.source,
            evaluation_score=row.evaluation_score, version=row.version, status=row.status,
            created_at=row.created_at or _now(), updated_at=row.updated_at or row.created_at or _now(),
        )


class SessionMemoryService:
    """Backend-neutral session memory with optional SQL fallback for local resilience."""

    def __init__(self) -> None:
        self._sql = SqlSessionMemoryRepository()
        self._mongo = MongoSessionMemoryRepository()

    @property
    def _primary(self) -> SessionMemoryRepository:
        if settings.SESSION_MEMORY_BACKEND.strip().lower() in {"mongo", "mongodb"}:
            return self._mongo
        return self._sql

    @property
    def backend_name(self) -> str:
        return self._primary.backend_name

    def _load(self, db: Session, **key: int | str) -> dict[str, Any] | None:
        try:
            return self._primary.load(db, **key)
        except Exception:
            if settings.MONGODB_REQUIRED or self._primary is self._sql:
                raise
            logger.exception("MongoDB session memory unavailable; falling back to SQL")
            return self._sql.load(db, **key)

    def _save(self, db: Session, record: dict[str, Any]) -> dict[str, Any]:
        try:
            return self._primary.save(db, record)
        except Exception:
            if settings.MONGODB_REQUIRED or self._primary is self._sql:
                raise
            logger.exception("MongoDB session memory write failed; falling back to SQL")
            return self._sql.save(db, record)

    def upsert(self, db: Session, *, tenant_id: int, user_id: int, thread_id: str, messages: list[dict], active_topic: str | None = None, unresolved_questions: list[dict] | None = None, confirmed_constraints: list[dict] | None = None) -> SessionMemory:
        record = self._load(db, tenant_id=tenant_id, user_id=user_id, thread_id=thread_id) or {
            "id": f"ses_{uuid4().hex}", "tenant_id": tenant_id, "user_id": user_id,
            "thread_id": thread_id, "rolling_summary": "",
            "active_topic": None, "active_entities": [], "unresolved_questions": [],
            "confirmed_constraints": [], "latest_corrections": [],
            "created_at": _now(), "updated_at": _now(),
        }
        record.pop("recent_messages", None)
        record["active_topic"] = active_topic or self._topic(messages) or record.get("active_topic")
        current_entities = record.get("active_entities") or []
        entity_map = {
            str(item.get("canonical_name", "")).lower(): item
            for item in [*self._entities(messages), *current_entities]
            if item.get("canonical_name")
        }
        record["active_entities"] = list(entity_map.values())[:20]
        record["unresolved_questions"] = unresolved_questions if unresolved_questions is not None else (record.get("unresolved_questions") or [])
        record["confirmed_constraints"] = confirmed_constraints if confirmed_constraints is not None else (record.get("confirmed_constraints") or [])
        record["rolling_summary"] = self._structured_summary(record)
        return self._response(self._save(db, record))

    def get(self, db: Session, *, tenant_id: int, user_id: int, thread_id: str) -> SessionMemory | None:
        record = self._load(db, tenant_id=tenant_id, user_id=user_id, thread_id=thread_id)
        return self._response(record) if record else None

    def rebuild_summary(self, db: Session, *, tenant_id: int, user_id: int, thread_id: str) -> SessionMemory:
        record = self._load(db, tenant_id=tenant_id, user_id=user_id, thread_id=thread_id)
        if not record:
            raise LookupError("Session memory not found")
        record.pop("recent_messages", None)
        record["rolling_summary"] = self._structured_summary(record)
        return self._response(self._save(db, record))

    @staticmethod
    def _structured_summary(record: dict[str, Any]) -> str:
        """Serialize key session facts only; raw user/assistant messages are excluded."""
        summary = {
            "active_topic": record.get("active_topic"),
            "active_entities": [
                {
                    "entity_type": item.get("entity_type"),
                    "canonical_name": item.get("canonical_name"),
                }
                for item in (record.get("active_entities") or [])[:20]
            ],
            "confirmed_constraints": (record.get("confirmed_constraints") or [])[:20],
            "unresolved_questions": (record.get("unresolved_questions") or [])[:10],
            "latest_corrections": (record.get("latest_corrections") or [])[:10],
        }
        return json.dumps(summary, ensure_ascii=False)[-settings.MEMORY_SUMMARY_CHAR_LIMIT:]

    def health(self) -> dict[str, Any]:
        try:
            return self._primary.health()
        except Exception as exc:
            return {
                "status": "unavailable" if settings.MONGODB_REQUIRED else "degraded",
                "backend": self.backend_name,
                "fallback": None if settings.MONGODB_REQUIRED else "sql",
                "detail": str(exc)[:300],
            }

    @staticmethod
    def _topic(messages: list[dict]) -> str | None:
        return next((str(item.get("content", ""))[:200] for item in reversed(messages) if item.get("role") == "user" and item.get("content")), None)

    @staticmethod
    def _entities(messages: list[dict]) -> list[dict]:
        now = datetime.now(timezone.utc)
        seen = set()
        entities = []
        pattern = re.compile(r"\b[A-Z][A-Z0-9-]{1,9}\b|[\u4e00-\u9fff]{2,8}(?:病|药|综合征|指标)")
        for item in reversed(messages):
            for match in pattern.findall(str(item.get("content", ""))):
                if match.lower() in seen:
                    continue
                seen.add(match.lower())
                entities.append(ActiveEntity(
                    entity_type="medical_or_project", canonical_name=match, aliases=[],
                    source_message_id=str(item.get("id", "unknown")), confidence=0.75,
                    last_mentioned_at=now,
                ).model_dump(mode="json"))
                if len(entities) >= 20:
                    return entities
        return entities

    @staticmethod
    def _response(record: dict[str, Any]) -> SessionMemory:
        return SessionMemory(
            thread_id=record["thread_id"], user_id=record["user_id"], tenant_id=record["tenant_id"],
            rolling_summary=record.get("rolling_summary") or "",
            active_topic=record.get("active_topic"),
            active_entities=[ActiveEntity.model_validate(item) for item in (record.get("active_entities") or [])],
            unresolved_questions=[UnresolvedQuestion.model_validate(item) for item in (record.get("unresolved_questions") or [])],
            confirmed_constraints=record.get("confirmed_constraints") or [], latest_corrections=record.get("latest_corrections") or [],
            last_updated_at=record.get("updated_at") or record.get("created_at") or _now(),
        )


agent_memory_service = AgentMemoryService()
session_memory_service = SessionMemoryService()
