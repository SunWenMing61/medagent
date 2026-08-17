"""Evidence verification agent with fail-closed authorization and memory rules."""

from __future__ import annotations

import re

from app.agents.registry import AgentDefinition, agent_registry
from app.agents.schemas import EvidenceVerificationResult, RetrievalPlan, RetrievedEvidence
from app.services.prompt_security_service import neutralize_untrusted_text
from app.services.evidence_service import evaluate_evidence_sufficiency


VERSION = "1.0.0"
_TOKEN = re.compile(r"[\w\u4e00-\u9fff]{2,}", re.I)
_NEGATION = re.compile(r"禁忌|不推荐|不得|无效|contraindicat|not recommended|no benefit", re.I)
_AFFIRMATION = re.compile(r"推荐|适用|有效|获益|recommended|effective|benefit", re.I)


def _relevance(query: str, content: str) -> float:
    query_terms = {item.lower() for item in _TOKEN.findall(query)}
    content_terms = {item.lower() for item in _TOKEN.findall(content)}
    token_score = len(query_terms & content_terms) / max(len(query_terms), 1)
    query_cjk = "".join(re.findall(r"[\u4e00-\u9fff]", query))
    content_cjk = "".join(re.findall(r"[\u4e00-\u9fff]", content))
    query_bigrams = {query_cjk[index:index + 2] for index in range(max(0, len(query_cjk) - 1))}
    content_bigrams = {content_cjk[index:index + 2] for index in range(max(0, len(content_cjk) - 1))}
    cjk_score = len(query_bigrams & content_bigrams) / max(len(query_bigrams), 1)
    return max(token_score, cjk_score)


class EvidenceVerifierAgent:
    name = "evidence_verifier"
    version = VERSION

    def run(
        self,
        plan: RetrievalPlan,
        evidence: list[dict],
        *,
        retrieval_had_system_error: bool = False,
    ) -> EvidenceVerificationResult:
        if retrieval_had_system_error and not evidence:
            return EvidenceVerificationResult(
                evidence_status="system_error",
                missing_information=["retrieval system unavailable"],
                recommended_action="refuse_answer",
                confidence=1.0,
                reason="Retrieval failed; a system error must not be presented as no evidence.",
            )

        query_terms = {item.lower() for item in _TOKEN.findall(plan.normalized_query)}
        supporting: list[str] = []
        rejected: list[str] = []
        positive: list[str] = []
        negative: list[str] = []

        for raw in evidence:
            item = RetrievedEvidence.model_validate(raw)
            if (
                not item.is_authorized
                or item.is_conversation_memory
                or not item.can_support_medical_claim
                or item.quality_status in {"manual_review_required", "blocked", "rejected"}
            ):
                rejected.append(item.evidence_id)
                continue
            content, injection = neutralize_untrusted_text(item.content)
            overlap = _relevance(plan.normalized_query, content)
            scored = max(item.rerank_score or 0.0, item.retrieval_score or 0.0)
            if injection or (overlap < 0.08 and scored < 0.2):
                rejected.append(item.evidence_id)
                continue
            supporting.append(item.evidence_id)
            if _NEGATION.search(content):
                negative.append(item.evidence_id)
            if _AFFIRMATION.search(content):
                positive.append(item.evidence_id)

        # The deterministic sufficiency layer checks entity/constraint coverage and
        # explicit recommendation/dosage conflicts across all authorized sources.
        analysis = evaluate_evidence_sufficiency(
            plan,
            [raw for raw in evidence if str(raw.get("evidence_id")) in supporting],
            retrieval_had_system_error=retrieval_had_system_error,
        )
        rejected = sorted(set(rejected + analysis["rejected"]))
        conflict_ids = sorted(set(analysis["conflicting"]))
        if not conflict_ids:
            conflict_ids = sorted(set(positive) & set(negative))
        if not conflict_ids and positive and negative:
            conflict_ids = sorted(set(positive + negative))
        if conflict_ids:
            return EvidenceVerificationResult(
                evidence_status="conflicting",
                supporting_evidence_ids=supporting,
                conflicting_evidence_ids=conflict_ids,
                rejected_evidence_ids=rejected,
                conflict_summary="Authorized sources contain materially different affirmative and negative guidance.",
                recommended_action="human_review",
                confidence=0.75,
                reason="Conflicting evidence requires explicit presentation or human review.",
            )
        if analysis["status"] in {"insufficient", "system_error"} or not supporting:
            return EvidenceVerificationResult(
                evidence_status=analysis["status"],
                rejected_evidence_ids=rejected,
                missing_information=analysis["missing"] or ["authorized evidence directly answering the query"],
                recommended_action="refuse_answer" if analysis["status"] == "system_error" else "retrieve_again",
                confidence=analysis["confidence"],
                reason=analysis["reason"],
            )
        return EvidenceVerificationResult(
            evidence_status="sufficient",
            supporting_evidence_ids=supporting,
            rejected_evidence_ids=rejected,
            recommended_action="generate_answer",
            confidence=analysis["confidence"],
            reason=analysis["reason"],
        )


evidence_verifier_agent = EvidenceVerifierAgent()
agent_registry.register(
    AgentDefinition(
        name=evidence_verifier_agent.name,
        version=VERSION,
        prompt_id="evidence_verifier",
        prompt_version="evidence_verifier_v1",
        output_schema=EvidenceVerificationResult,
        model_setting="EVIDENCE_MODEL",
    ),
    evidence_verifier_agent,
)
