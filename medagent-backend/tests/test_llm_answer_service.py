import json

import pytest

from app.core.config import settings
from app.services.llm_answer_service import LLMAnswerService


class _Response:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": self.content}}]}


class _Client:
    def __init__(self, contents):
        self.contents = list(contents)
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return _Response(self.contents.pop(0))


def _configure(monkeypatch):
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    monkeypatch.setattr(settings, "LLM_API_BASE", "https://example.test/v1")
    monkeypatch.setattr(settings, "LLM_MODEL", "test-model")
    monkeypatch.setattr(settings, "LLM_ANSWER_GENERATION_ENABLED", True)


def test_direct_answer_removes_hidden_reasoning_and_normalizes_spacing(monkeypatch):
    _configure(monkeypatch)
    client = _Client(["<think>internal</think> 这是一个  通顺的回答。\n\n\n第二段。"])
    answer = LLMAnswerService(client=client).generate_direct("解释 Python 列表", style="concise_evidence")
    assert answer.summary == "这是一个 通顺的回答。\n\n第二段。"
    assert answer.details == []
    assert client.requests[0][0] == "https://example.test/v1/chat/completions"
    assert client.requests[0][1]["json"]["model"] == "test-model"
    system_prompt = client.requests[0][1]["json"]["messages"][0]["content"]
    assert "MedAgent" in system_prompt
    assert "test-model" in system_prompt
    assert "不要声称自己是‘最新版’" in system_prompt


def test_grounded_answer_repairs_ocr_text_but_preserves_evidence_id(monkeypatch):
    _configure(monkeypatch)
    content = json.dumps({
        "summary": "高血压管理需要综合考虑。",
        "details": [{
            "claim": "通常需要结合生活方式干预和专业评估。",
            "citation_ids": ["ev_1234567890abcdef"],
            "confidence": 0.88,
        }],
        "uncertainty": "具体方案因人而异。",
        "limitations": ["不能代替个人诊疗。"],
        "recommended_next_step": "请咨询医生。",
        "needs_professional_consultation": True,
    }, ensure_ascii=False)
    service = LLMAnswerService(client=_Client([f"```json\n{content}\n```"]))
    answer = service.generate_grounded(
        "高血压怎么管理？",
        [{
            "evidence_id": "ev_1234567890abcdef",
            "source_name": "test-kb",
            "content": "高血压 管 理需 要生 活方式干 预。",
        }],
        style="concise_evidence",
        general_mode=False,
    )
    assert answer.details[0].claim == "通常需要结合生活方式干预和专业评估。"
    assert answer.details[0].citation_ids == ["ev_1234567890abcdef"]


def test_grounded_answer_rejects_invented_citation(monkeypatch):
    _configure(monkeypatch)
    content = json.dumps({
        "summary": "摘要",
        "details": [{"claim": "结论", "citation_ids": ["ev_invented000001"], "confidence": 0.8}],
    }, ensure_ascii=False)
    service = LLMAnswerService(client=_Client([content]))
    with pytest.raises(ValueError, match="allowed evidence citation"):
        service.generate_grounded(
            "问题",
            [{"evidence_id": "ev_1234567890abcdef", "source_name": "kb", "content": "证据"}],
            style="concise_evidence",
            general_mode=False,
        )
