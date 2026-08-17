"""Rule-first input triage agent; emergency detection never depends on an LLM."""

from __future__ import annotations

import re

from app.agents.registry import AgentDefinition, agent_registry
from app.agents.schemas import InputTriageResult
from app.services.safety_service import RiskLevel, safety_service


VERSION = "1.0.0"
PROMPT_ID = "input_triage"
PROMPT_VERSION = "input_triage_v1"

_DRUG = re.compile(r"药|用药|副作用|相互作用|drug|medication|dose|剂量|说明书", re.I)
_PAPER = re.compile(r"论文|文献|研究|指南|PMID|PubMed|meta[- ]?analysis", re.I)
_SYMPTOM = re.compile(r"疼|痛|发热|咳|吐|晕|乏力|症状|不舒服|symptom|ache|fever", re.I)
_DOCUMENT = re.compile(r"这份|本文|文档|附件|总结|概括|document|attachment|summari", re.I)
_MEMORY = re.compile(r"之前|刚才|上次|我提到|remember|previous", re.I)
_MEDICAL = re.compile(
    r"病|医|治疗|检查|健康|药|症|血压|血糖|胆固醇|感染|肿瘤|营养|康复|"
    r"disease|medical|health|clinical|blood pressure|glucose|cholesterol",
    re.I,
)
_HIGH_RISK = re.compile(
    r"诊断|处方|开药|停药|换药|调整剂量|加量|减量|孕|妊娠|儿童|婴儿|老人|老年|相互作用|恶化|"
    r"diagnos|prescri|stop taking|change medication|adjust.*dose|pregnan|child|elderly|interaction|worsen",
    re.I,
)
_DURATION = re.compile(r"\d+\s*(秒|分钟|小时|天|周|月|年)|突然|持续|反复|多久", re.I)


class InputTriageAgent:
    name = "input_triage"
    version = VERSION

    def run(self, query: str, assistant_profile: str = "memory_qa") -> InputTriageResult:
        query = (query or "").strip()
        assessment = safety_service.assess(query)
        emergency = assessment.level in {RiskLevel.EMERGENCY, RiskLevel.SELF_HARM}

        if emergency:
            return InputTriageResult(
                intent="emergency_risk",
                risk_level="emergency",
                need_emergency_response=True,
                need_clarification=False,
                required_routes=[],
                medical_entities=[],
                constraints=[],
                reason="Rule-first emergency or self-harm pattern matched.",
            )

        if _DRUG.search(query):
            intent = "drug_information"
        elif _PAPER.search(query):
            intent = "literature_search"
        elif _DOCUMENT.search(query):
            intent = "document_summary"
        elif _MEMORY.search(query):
            intent = "medical_knowledge"
        elif _SYMPTOM.search(query):
            intent = "symptom_consultation"
        elif _MEDICAL.search(query):
            intent = "medical_knowledge"
        elif assistant_profile == "general_qa":
            intent = "general_knowledge"
        else:
            intent = "out_of_scope"

        boundary_high = bool(_HIGH_RISK.search(query))
        urgent = assessment.level == RiskLevel.URGENT
        risk = "high" if boundary_high or urgent else ("medium" if intent == "symptom_consultation" else "low")
        needs_clarification = bool(
            intent == "symptom_consultation" and not _DURATION.search(query) and len(query) < 100
        )
        routes: list[str] = []
        if intent not in {"out_of_scope", "general_knowledge"}:
            routes.append("local_rag")
        if assistant_profile == "general_qa" and intent not in {"general_knowledge", "document_summary", "out_of_scope"}:
            routes.append("online_web")
        if intent in {"literature_search", "drug_information"}:
            routes.append("online_medical_source")
        if intent == "document_summary":
            routes.append("document_summary")

        topics = ["症状开始方式", "持续时间和严重程度", "伴随的危险症状"] if needs_clarification else []
        return InputTriageResult(
            intent=intent,
            risk_level=risk,
            need_emergency_response=False,
            need_clarification=needs_clarification,
            clarification_topics=topics,
            required_routes=routes,
            medical_entities=[],
            constraints=[match.group(0) for match in _HIGH_RISK.finditer(query)],
            reason=(
                "Rule-first triage completed; non-medical general knowledge goes directly to the LLM, "
                "while medical questions combine authorized local knowledge with whitelisted web search."
                if assistant_profile == "general_qa"
                else "Rule-first triage completed; semantic routing is constrained to whitelisted paths."
            ),
        )


input_triage_agent = InputTriageAgent()
agent_registry.register(
    AgentDefinition(
        name=input_triage_agent.name,
        version=VERSION,
        prompt_id=PROMPT_ID,
        prompt_version=PROMPT_VERSION,
        output_schema=InputTriageResult,
        model_setting="TRIAGE_MODEL",
    ),
    input_triage_agent,
)
