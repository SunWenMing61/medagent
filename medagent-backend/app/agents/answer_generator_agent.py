"""Citation-bound answer generator that can only see verified evidence."""

from __future__ import annotations

import re

from app.agents.registry import AgentDefinition, agent_registry
from app.agents.schemas import ClaimWithEvidence, RetrievedEvidence, StructuredAnswer
from app.core.config import settings
from app.services.llm_answer_service import llm_answer_service


VERSION = "1.0.0"


def _first_sentences(content: str, limit: int = 260) -> str:
    value = re.split(r"(?<=[。！？.!?])\s+", content.strip())[0]
    return value[:limit].strip()


def _evidence_excerpt(content: str, *, sentence_count: int, limit: int) -> str:
    normalized = re.sub(r"\s+", " ", (content or "").strip())
    sentences = [item.strip() for item in re.split(r"(?<=[。！？.!?])\s*", normalized) if item.strip()]
    selected: list[str] = []
    for sentence in sentences:
        candidate = " ".join(selected + [sentence])
        if selected and len(candidate) > limit:
            break
        if len(sentence) > limit:
            clauses = [item.strip() for item in re.split(r"(?<=[，,；;：:])", sentence) if item.strip()]
            shortened = ""
            for clause in clauses:
                if shortened and len(shortened + clause) > limit - 1:
                    break
                shortened += clause
            sentence = shortened.rstrip("，,；;：:") + "。" if shortened else ""
        if sentence:
            selected.append(sentence)
        if len(selected) >= sentence_count:
            break
    return " ".join(selected).strip()


class ConciseAnswerGeneratorAgent:
    name = "answer_generator_concise"
    version = VERSION

    def run(
        self,
        query: str,
        verified_evidence: list[dict],
        *,
        rewrite: bool = False,
        general_mode: bool = False,
    ) -> StructuredAnswer:
        items = [RetrievedEvidence.model_validate(item) for item in verified_evidence]
        if general_mode and not items and settings.LLM_ANSWER_GENERATION_ENABLED:
            try:
                return llm_answer_service.generate_direct(query, style="concise_evidence")
            except Exception:
                return StructuredAnswer(
                    summary="大模型服务当前暂时不可用，请稍后重试。",
                    details=[],
                    needs_professional_consultation=False,
                )
        if not items:
            return StructuredAnswer(
                summary=(
                    "目前没有找到足够的知识库或联网证据回答这个问题。"
                    if general_mode
                    else "目前没有足够的、经过核验的医学证据回答这个问题。"
                ),
                limitations=["未找到可授权引用的直接证据。"],
                recommended_next_step="请补充问题范围，或咨询合格的医疗专业人员。",
                needs_professional_consultation=True,
            )

        if settings.LLM_ANSWER_GENERATION_ENABLED:
            try:
                return llm_answer_service.generate_grounded(
                    query,
                    [item.model_dump(mode="json") for item in items[:4]],
                    style="concise_evidence",
                    general_mode=general_mode,
                )
            except Exception:
                pass
        details = [
            ClaimWithEvidence(
                claim=_evidence_excerpt(item.content, sentence_count=1, limit=220),
                citation_ids=[item.evidence_id],
                confidence=min(0.95, max(0.5, item.rerank_score or item.retrieval_score or 0.7)),
            )
            for item in items[:4]
            if _evidence_excerpt(item.content, sentence_count=1, limit=220)
        ]
        summary = (
            "精炼结论：根据知识库与联网检索到的已核验来源，核心信息如下。"
            if general_mode
            else "精炼结论：根据已核验来源，核心信息如下。"
        )
        if rewrite:
            summary = "以下内容已按医疗安全边界重新表述，仅作为一般信息参考。"
        if general_mode:
            return StructuredAnswer(
                summary=summary,
                details=details,
                uncertainty="联网搜索摘要可能不完整或存在更新延迟，请以引用页面原文为准。",
                limitations=["回答仅使用本次检索并通过核验的知识库与互联网证据。"],
                recommended_next_step="如需进一步确认，可打开引用链接核对原文和更新时间。",
                needs_professional_consultation=False,
            )
        return StructuredAnswer(
            summary=summary,
            details=details,
            uncertainty="证据可能不覆盖你的全部个人病史、检查结果和合并用药情况。",
            limitations=["不能据此作出个人诊断、处方、停药换药或剂量调整。"],
            recommended_next_step="涉及个人症状或用药决策时，请咨询医生或药师。",
            needs_professional_consultation=True,
        )


class DetailedAnswerGeneratorAgent:
    name = "answer_generator_detailed"
    version = VERSION

    def run(
        self,
        query: str,
        verified_evidence: list[dict],
        *,
        rewrite: bool = False,
        general_mode: bool = False,
    ) -> StructuredAnswer:
        items = [RetrievedEvidence.model_validate(item) for item in verified_evidence]
        if general_mode and not items and settings.LLM_ANSWER_GENERATION_ENABLED:
            try:
                return llm_answer_service.generate_direct(query, style="detailed_guidance")
            except Exception:
                return StructuredAnswer(
                    summary="大模型服务当前暂时不可用，请稍后重试。",
                    details=[],
                    needs_professional_consultation=False,
                )
        if not items:
            return StructuredAnswer(
                summary=(
                    "目前没有找到足够的知识库或联网证据回答这个问题。"
                    if general_mode
                    else "目前没有足够的、经过核验的医学证据回答这个问题。"
                ),
                limitations=["未找到可授权引用的直接证据。"],
                recommended_next_step="请补充问题范围，或咨询合格的医疗专业人员。",
                needs_professional_consultation=True,
            )
        if settings.LLM_ANSWER_GENERATION_ENABLED:
            try:
                return llm_answer_service.generate_grounded(
                    query,
                    [item.model_dump(mode="json") for item in items[:4]],
                    style="detailed_guidance",
                    general_mode=general_mode,
                )
            except Exception:
                pass
        details = [
            ClaimWithEvidence(
                claim=_evidence_excerpt(item.content, sentence_count=2, limit=460),
                citation_ids=[item.evidence_id],
                confidence=min(0.95, max(0.5, item.rerank_score or item.retrieval_score or 0.7)),
            )
            for item in items[:4]
            if _evidence_excerpt(item.content, sentence_count=2, limit=460)
        ]
        summary = (
            "详细说明：以下按知识库与联网证据来源展开，并标明核验边界。"
            if general_mode
            else "详细说明：以下按证据来源展开，并保留适用边界与下一步建议。"
        )
        if rewrite:
            summary = "以下详细内容已按医疗安全边界重新表述，仅作为一般信息参考。"
        if general_mode:
            return StructuredAnswer(
                summary=summary,
                details=details,
                uncertainty="互联网内容可能随时间变化，搜索摘要也可能省略原文限定条件。",
                limitations=[
                    "回答只使用本次已核验且有权限访问的知识库与联网证据。",
                    "请打开引用页面核对完整上下文、发布时间和更新时间。",
                ],
                recommended_next_step="如问题依赖最新状态，建议优先查看引用链接中的发布日期与原文。",
                needs_professional_consultation=False,
            )
        return StructuredAnswer(
            summary=summary,
            details=details,
            uncertainty="不同来源的适用人群、研究设计和更新时间可能不同，且证据不能覆盖个人完整病史。",
            limitations=[
                "回答只使用本次已核验且有权限访问的证据。",
                "不能据此作出个人诊断、处方、停药换药或剂量调整。",
            ],
            recommended_next_step="可结合引用原文继续核对；涉及个人症状或用药决策时，请咨询医生或药师。",
            needs_professional_consultation=True,
        )


answer_generator_concise_agent = ConciseAnswerGeneratorAgent()
answer_generator_detailed_agent = DetailedAnswerGeneratorAgent()
# Compatibility alias for callers that imported the original singleton.
answer_generator_agent = answer_generator_concise_agent

for instance, prompt_id in (
    (answer_generator_concise_agent, "answer_generator_concise"),
    (answer_generator_detailed_agent, "answer_generator_detailed"),
):
    agent_registry.register(
        AgentDefinition(
            name=instance.name,
            version=VERSION,
            prompt_id=prompt_id,
            prompt_version=f"{prompt_id}_v1",
            output_schema=StructuredAnswer,
            model_setting="ANSWER_MODEL",
            uses_model=True,
        ),
        instance,
    )
