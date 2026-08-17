"""OpenAI-compatible answer generation with strict output normalization.

The service has two modes:
- direct general QA, where no retrieval evidence is required;
- evidence-grounded rewriting, where every detail must retain allowed evidence IDs.

Secrets are read only from server settings and are never logged or returned.
"""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import settings


_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.I | re.S)
_BROKEN_CHARS = re.compile(r"[\ufffd]|(?:Ã.|Â.|â€|锟斤拷)")


class LLMAnswerService:
    def __init__(self, client: httpx.Client | None = None) -> None:
        self.client = client or httpx.Client(timeout=httpx.Timeout(35.0, connect=5.0))

    def generate_direct(self, query: str, *, style: str):
        from app.agents.schemas import StructuredAnswer

        style_instruction = (
            "先直接回答核心问题，再用不超过 4 个要点补充；避免重复和套话。"
            if style == "concise_evidence"
            else "先给结论，再分层解释原因、示例和注意事项；结构清楚但不要堆砌内容。"
        )
        content = self._chat(
            system=(
                f"你是 MedAgent 通用问答助手，当前后端配置的生成模型标识为 {settings.LLM_MODEL}。"
                "如果用户询问你是谁或使用哪个模型，应如实说明你是 MedAgent，回答由该配置模型生成；"
                "不要冒充模型供应商本身，也不要声称自己是‘最新版’。"
                "请直接、自然、准确地回答用户，不要声称问题超出医学范围，"
                "不要提及知识库、检索流程或内部 Agent。默认使用简体中文；若用户明确使用其他语言，"
                "则使用相同语言。自动修正输入中的明显错别字，但不要改变问题含义。"
                "保证语句完整通顺，禁止输出乱码、拼音式中文、OCR 残片或半截句子。"
                "不确定的事实要明确说明，涉及实时信息时提醒用户核对日期。"
                "除非系统明确提供，否则不要编造免费政策、知识截止日期、上下文长度或产品功能。"
            ),
            user=f"回答风格：{style_instruction}\n\n用户问题：\n{query}",
            max_tokens=1200 if style == "concise_evidence" else 2000,
            temperature=0.25,
        )
        return StructuredAnswer(
            summary=self._clean_text(content),
            details=[],
            needs_professional_consultation=False,
        )

    def generate_grounded(
        self,
        query: str,
        evidence: list[dict[str, Any]],
        *,
        style: str,
        general_mode: bool,
    ):
        from app.agents.schemas import StructuredAnswer

        evidence_payload = [
            {
                "evidence_id": str(item.get("evidence_id") or ""),
                "source_name": str(item.get("source_name") or ""),
                "content": str(item.get("content") or "")[:2400],
            }
            for item in evidence
        ]
        style_instruction = (
            "精炼版：summary 用 1 至 2 句概括；details 保留最多 4 条最关键结论。"
            if style == "concise_evidence"
            else "详细版：summary 先概括；details 按逻辑顺序解释，最多 6 条，避免重复。"
        )
        medical_instruction = (
            "这是一般知识问答，不要添加医疗免责声明。"
            if general_mode
            else "这是医疗健康内容，只能做一般信息说明，不得给出个人诊断、处方或自行调药建议。"
        )
        raw = self._chat(
            system=(
                "你是证据约束的中文回答编辑。只能根据给定证据作答，不得引入证据之外的新事实。"
                "你的任务不是复制证据，而是修复 OCR 错字、断行、重复、网页摘要残句和不自然表达，"
                "将其改写为完整、准确、通顺的简体中文。禁止拼音式中文、乱码和半截句子。"
                "每条 details.claim 必须引用实际支持它的 evidence_id。"
                "严格输出一个 JSON 对象，不要输出 Markdown 代码块或额外说明。"
            ),
            user=(
                f"{style_instruction}\n{medical_instruction}\n"
                "JSON 格式："
                '{"summary":"...","details":[{"claim":"...","citation_ids":["ev_..."],"confidence":0.8}],'
                '"uncertainty":"...或null","limitations":["..."],'
                '"recommended_next_step":"...或null","needs_professional_consultation":false}'
                f"\n\n用户问题：\n{query}\n\n可用证据：\n"
                + json.dumps(evidence_payload, ensure_ascii=False)
            ),
            max_tokens=1600 if style == "concise_evidence" else 2600,
            temperature=0.15,
        )
        parsed = self._parse_json(raw)
        answer = StructuredAnswer.model_validate(parsed)
        if not answer.details:
            raise ValueError("Grounded model answer must contain at least one cited detail")
        allowed = {item["evidence_id"] for item in evidence_payload}
        for detail in answer.details:
            if not detail.citation_ids or not set(detail.citation_ids).issubset(allowed):
                raise ValueError("Model returned a claim without an allowed evidence citation")
            detail.claim = self._clean_text(detail.claim)
        answer.summary = self._clean_text(answer.summary)
        if answer.uncertainty:
            answer.uncertainty = self._clean_text(answer.uncertainty)
        answer.limitations = [self._clean_text(item) for item in answer.limitations if item.strip()]
        if answer.recommended_next_step:
            answer.recommended_next_step = self._clean_text(answer.recommended_next_step)
        return answer

    def _chat(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int,
        temperature: float,
    ) -> str:
        if not settings.LLM_API_KEY:
            raise RuntimeError("LLM_API_KEY is not configured")
        base = settings.LLM_API_BASE.rstrip("/")
        endpoint = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        response = self.client.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.LLM_MODEL,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Model returned an empty answer")
        return content

    @staticmethod
    def _parse_json(value: str) -> dict[str, Any]:
        cleaned = _THINK_BLOCK.sub("", value).strip()
        cleaned = _CODE_FENCE.sub("", cleaned).strip()
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Model did not return a JSON object")
        result = json.loads(cleaned[start:end + 1])
        if not isinstance(result, dict):
            raise ValueError("Model JSON answer must be an object")
        return result

    @staticmethod
    def _clean_text(value: str) -> str:
        cleaned = _THINK_BLOCK.sub("", value or "")
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if not cleaned:
            raise ValueError("Answer text is empty after normalization")
        if _BROKEN_CHARS.search(cleaned):
            raise ValueError("Answer contains encoding-corruption markers")
        return cleaned


llm_answer_service = LLMAnswerService()
