from unittest.mock import patch

from app.agents.schemas import StructuredAnswer
from app.api.v1.chat import _response
from app.core.config import settings
from app.graphs.graph_state import new_agent_state
from app.graphs.root_graph import build_controlled_workflow
from app.tools.schemas import OnlineRetrievalInput, ToolContext
from app.tools.web_search_tool import WebSearchTool


class _Response:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


class _DuckDuckGoClient:
    def get(self, url, **kwargs):
        assert url == "https://api.duckduckgo.com/"
        assert kwargs["params"]["q"] == "Python list sort"
        return _Response({
            "Heading": "Sorting Python lists",
            "AbstractText": "Python lists can be sorted in place with list.sort or copied with sorted.",
            "AbstractURL": "https://docs.python.org/3/howto/sorting.html",
            "RelatedTopics": [],
        })


def test_keyless_web_search_uses_public_fallback(monkeypatch):
    monkeypatch.setattr(settings, "SEARCH_API_KEY", None)
    result = WebSearchTool(client=_DuckDuckGoClient()).execute(OnlineRetrievalInput(
        context=ToolContext(request_id="req", user_id=1, tenant_id=1),
        query="Python list sort",
        max_results=1,
    ))
    assert result.status == "success"
    assert result.evidence[0].source_type == "web_search"
    assert result.evidence[0].metadata["provider"] == "duckduckgo"
    assert result.evidence[0].url == "https://docs.python.org/3/howto/sorting.html"


def test_non_medical_general_qa_goes_directly_to_the_model(monkeypatch):
    monkeypatch.setattr(settings, "LLM_ANSWER_GENERATION_ENABLED", True)

    def fake_direct(query, *, style):
        assert query == "How do I sort a Python list?"
        label = "精炼" if style == "concise_evidence" else "详细"
        return StructuredAnswer(summary=f"{label}回答：可以使用 list.sort() 或 sorted()。")

    with patch(
        "app.agents.answer_generator_agent.llm_answer_service.generate_direct",
        side_effect=fake_direct,
    ) as model_call:
        result = build_controlled_workflow(persist=False, trace=False).run(new_agent_state(
            raw_query="How do I sort a Python list?",
            user_id=1,
            tenant_id=1,
            authorized_kb_ids=[],
            assistant_profile="general_qa",
            persistent_memory_enabled=False,
        ))
    assert result["status"] == "completed"
    assert result["intent"] == "general_knowledge"
    assert result["evidence_status"] == "not_run"
    assert result["tool_call_count"] == 0
    assert result["citations"] == []
    assert "list.sort" in result["final_answer"]
    assert len(result["answer_variants"]) == 2
    assert model_call.call_count == 2
    assert "医疗免责声明" not in result["final_answer"]


def test_general_direct_response_omits_medical_disclaimer():
    class Session:
        id = 99

    response = _response(
        Session(),
        "你是谁？",
        {"intent": "general_knowledge", "citations": []},
        "我是 MedAgent。",
        "medical disclaimer",
        "general_qa",
    )
    assert response.disclaimer is None
