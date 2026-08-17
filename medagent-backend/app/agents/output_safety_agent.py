"""Final output safety agent; failure and high risk are fail-closed."""

from __future__ import annotations

from app.agents.registry import AgentDefinition, agent_registry
from app.agents.schemas import SafetyReviewResult, StructuredAnswer
from app.services.safety_service import safety_service


VERSION = "1.0.0"


class OutputSafetyAgent:
    name = "output_safety"
    version = VERSION

    def run(
        self,
        answer: StructuredAnswer,
        *,
        allowed_evidence_ids: set[str],
        risk_level: str,
    ) -> SafetyReviewResult:
        rendered = "\n".join([answer.summary] + [item.claim for item in answer.details])
        unsafe = safety_service.check_output(rendered)
        unsupported = [
            item.claim
            for item in answer.details
            if not item.citation_ids or any(citation not in allowed_evidence_ids for citation in item.citation_ids)
        ]
        if unsupported:
            return SafetyReviewResult(
                safety_status="blocked",
                risk_categories=["unsupported_medical_claim"],
                unsupported_claims=unsupported,
                rewrite_instructions=["Remove every claim that lacks an allowed evidence ID."],
                final_disclaimer_required=True,
                reason="At least one claim is not bound to verified evidence.",
            )
        if unsafe:
            status = "human_review_required" if risk_level in {"high", "emergency"} else "rewrite_required"
            return SafetyReviewResult(
                safety_status=status,
                risk_categories=["diagnosis_or_prescribing_boundary"],
                unsafe_spans=unsafe,
                rewrite_instructions=["Use educational, non-directive wording and remove diagnosis/dose/medication changes."],
                final_disclaimer_required=True,
                reason="The draft crossed a deterministic medical-output boundary.",
            )
        return SafetyReviewResult(
            safety_status="pass",
            final_disclaimer_required=answer.needs_professional_consultation,
            reason="All medical claims are evidence-bound and no prohibited directive was detected.",
        )


output_safety_agent = OutputSafetyAgent()
agent_registry.register(
    AgentDefinition(
        name=output_safety_agent.name,
        version=VERSION,
        prompt_id="output_safety",
        prompt_version="output_safety_v1",
        output_schema=SafetyReviewResult,
        model_setting="SAFETY_MODEL",
    ),
    output_safety_agent,
)
