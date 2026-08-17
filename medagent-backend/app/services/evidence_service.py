"""Deterministic evidence normalization, deduplication, fusion and budgeting."""

from __future__ import annotations

import hashlib
import re

from app.chunking.token_counter import count_tokens
from app.core.config import settings


_NEGATIVE_GUIDANCE = re.compile(r"禁忌|不推荐|不得|无效|contraindicat|not recommended|no benefit", re.I)
_POSITIVE_GUIDANCE = re.compile(r"推荐|适用|有效|获益|recommended|effective|benefit", re.I)
_DOSAGE = re.compile(r"(?<!\d)(\d+(?:\.\d+)?)\s*(mg|g|μg|mcg|ml|mL)(?:\s*/\s*(?:d|day|日|次))?", re.I)


def evaluate_evidence_sufficiency(plan, evidence: list[dict], *, retrieval_had_system_error: bool = False) -> dict:
    """Evaluate coverage and conflicts without allowing Memory to become evidence."""
    if retrieval_had_system_error and not evidence:
        return {
            "status": "system_error", "confidence": 1.0, "supporting": [], "rejected": [],
            "conflicting": [], "missing": ["retrieval system unavailable"],
            "reason": "Retrieval failed; system failure is distinct from no evidence.",
        }

    supporting: list[str] = []
    rejected: list[str] = []
    contents: dict[str, str] = {}
    entities = [item.original_text for item in plan.entities]
    matched_entities: set[str] = set()
    missing_constraints: set[str] = set()
    positive: list[str] = []
    negative: list[str] = []
    dosage_values: dict[str, set[str]] = {}

    for item in evidence:
        evidence_id = str(item.get("evidence_id") or "")
        content = str(item.get("content") or "")
        if (
            not item.get("is_authorized", False)
            or item.get("is_conversation_memory", False)
            or not item.get("can_support_medical_claim", True)
            or item.get("quality_status") in {"manual_review_required", "blocked", "rejected"}
        ):
            if evidence_id:
                rejected.append(evidence_id)
            continue
        if evidence_id:
            supporting.append(evidence_id)
            contents[evidence_id] = content
        lower = content.casefold()
        matched_entities.update(entity for entity in entities if entity.casefold() in lower)
        constraint = (item.get("metadata") or {}).get("constraint_match") or {}
        for key in ("missing_numeric_constraints", "missing_population_constraints", "missing_time_constraints"):
            missing_constraints.update(str(value) for value in constraint.get(key, []))
        if constraint.get("negation_consistent") is False:
            missing_constraints.add("negation")
        if _POSITIVE_GUIDANCE.search(content):
            positive.append(evidence_id)
        if _NEGATIVE_GUIDANCE.search(content):
            negative.append(evidence_id)
        values = {f"{match[0]} {match[1].lower()}" for match in _DOSAGE.findall(content)}
        if values:
            dosage_values[evidence_id] = values

    conflicts: set[str] = set()
    if positive and negative:
        conflicts.update(positive + negative)
    unique_dosages = {value for values in dosage_values.values() for value in values}
    if len(unique_dosages) > 1:
        conflicts.update(dosage_values)
    if conflicts:
        return {
            "status": "conflicting", "confidence": 0.8, "supporting": supporting,
            "rejected": rejected, "conflicting": sorted(conflicts), "missing": [],
            "reason": "Authorized sources contain conflicting recommendations or dosage values.",
        }

    missing_entities = sorted(set(entities) - matched_entities)
    # A constraint may be absent from one result yet covered by another.
    all_text = "\n".join(contents.values()).casefold()
    unresolved_constraints = sorted(value for value in missing_constraints if value and value.casefold() not in all_text)
    if not supporting or (entities and len(matched_entities) == 0) or unresolved_constraints:
        missing = []
        if not supporting:
            missing.append("authorized evidence directly answering the query")
        missing.extend(missing_entities)
        missing.extend(unresolved_constraints)
        return {
            "status": "insufficient", "confidence": 0.9, "supporting": supporting,
            "rejected": rejected, "conflicting": [], "missing": list(dict.fromkeys(missing)),
            "reason": "Evidence does not cover the requested entities and constraints.",
        }
    return {
        "status": "sufficient", "confidence": min(0.96, 0.68 + 0.07 * len(supporting)),
        "supporting": supporting, "rejected": rejected, "conflicting": [], "missing": missing_entities,
        "reason": "Authorized evidence covers the requested subject and constraints.",
    }


def normalize_and_fuse(groups: list[list[dict]]) -> list[dict]:
    fused: dict[str, dict] = {}
    for source_rank, group in enumerate(groups):
        for rank, raw in enumerate(group, start=1):
            item = dict(raw)
            key = item.get("url") or hashlib.sha256(item.get("content", "").encode("utf-8")).hexdigest()
            current = fused.setdefault(key, item)
            current["rrf_score"] = float(current.get("rrf_score") or 0.0) + 1.0 / (settings.RRF_K + rank)
            current.setdefault("metadata", {})["source_rank"] = source_rank
    ranked = sorted(
        fused.values(),
        key=lambda item: (
            -float(item.get("exact_match_score") or 0.0),
            -int(item.get("authority_level") or 0),
            -float(item.get("rerank_score") or item.get("rrf_score") or 0.0),
            str(item.get("evidence_id")),
        ),
    )
    result = []
    used_tokens = 0
    for item in ranked:
        tokens = count_tokens(item.get("content", ""))
        if result and used_tokens + tokens > settings.EVIDENCE_MAX_TOKENS:
            continue
        result.append(item)
        used_tokens += tokens
        if len(result) >= settings.EVIDENCE_MAX_CHUNKS:
            break
    return result


def bind_public_citations(answer: dict, verified: list[dict]) -> tuple[list[dict], list[str]]:
    allowed = {item["evidence_id"]: item for item in verified}
    used: list[str] = []
    for claim in answer.get("details", []):
        for evidence_id in claim.get("citation_ids", []):
            if evidence_id not in allowed:
                raise ValueError("Answer contains a citation outside verified evidence")
            if evidence_id not in used:
                used.append(evidence_id)
    citations = []
    for evidence_id in used:
        item = allowed[evidence_id]
        citations.append({
            "evidence_id": evidence_id,
            "source_type": item.get("source_type"),
            "source_name": item.get("source_name"),
            "document_id": item.get("document_id"),
            "chunk_id": item.get("chunk_id"),
            "page_num": item.get("page_num"),
            "section_title": item.get("section_title"),
            "url": item.get("url"),
            "pmid": item.get("pmid"),
            "publication_date": item.get("publication_date"),
            "updated_at": item.get("updated_at"),
        })
    return citations, used
