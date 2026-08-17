"""Focused acceptance tests for the PDF cleaning and governed-tool v2 pipeline."""

from __future__ import annotations

import time

import fitz
from pydantic import BaseModel, ConfigDict

from app.chunking.structural_splitter import StructuralSplitter
from app.core.config import settings
from app.parsers.cleaning import clean_preserving_structure
from app.parsers.models import ParsedDocument, ParsedPage, ParsedTable, TextBlock
from app.parsers.page_classifier import classify_page
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolDefinition, ToolRegistry
from app.tools.schemas import AgentRuntimeContext, ToolContext, ToolError, ToolResult


def _runtime(**overrides) -> AgentRuntimeContext:
    values = {
        "request_id": "req-pdf-tool-v2",
        "thread_id": "thread-pdf-tool-v2",
        "user_id": 7,
        "tenant_id": 9,
        "authorized_kb_ids": [11],
        "permission_scopes": {"kb:read"},
        "agent_name": "retrieval",
        "intent": "medical_qa",
        "risk_level": "low",
        "workflow_stage": "retrieval",
        "online_search_enabled": False,
        "remaining_tool_calls": 5,
        "remaining_token_budget": 1000,
    }
    values.update(overrides)
    return AgentRuntimeContext(**values)


class _ProbeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context: ToolContext
    value: str


class _Implementation:
    def __init__(self, outcomes=None, delay: float = 0):
        self.inputs = []
        self.outcomes = list(outcomes or [])
        self.delay = delay

    def execute(self, value: _ProbeInput):
        self.inputs.append(value)
        if self.delay:
            time.sleep(self.delay)
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return ToolResult(status="success", data={"value": value.value})


def _executor(name: str, implementation: _Implementation, **definition_overrides) -> ToolExecutor:
    registry = ToolRegistry()
    definition_values = dict(
        name=name,
        version="2.0.0",
        input_schema=_ProbeInput,
        allowed_agents=frozenset({"retrieval"}),
        required_scopes=frozenset({"kb:read"}),
        cache_ttl_seconds=60,
    )
    definition_values.update(definition_overrides)
    definition = ToolDefinition(**definition_values)
    registry.register(definition, implementation)
    return ToolExecutor(registry)


def test_cleaning_is_traceable_and_preserves_medical_symbols():
    pages = []
    for page_num in (1, 2):
        pages.append(ParsedPage(
            page_num,
            f"临床指南\nSpO₂ ≥ 95%，剂量 O.5 mg，micro-\nvascular。\n第 {page_num} 页",
            "ocr",
            ocr_confidence=0.82,
            blocks=[
                TextBlock("临床指南", kind="header", block_id=f"p{page_num}_h"),
                TextBlock("SpO₂ ≥ 95%，剂量 O.5 mg，micro-\nvascular。", confidence=0.82, extraction_method="ocr", block_id=f"p{page_num}_b"),
                TextBlock(f"第 {page_num} 页", kind="page_number", block_id=f"p{page_num}_f"),
            ],
        ))
    document = clean_preserving_structure(ParsedDocument("medical.pdf", "pdf", "v2", pages))

    assert "SpO₂ ≥ 95%" in document.text
    assert "0.5 mg" in document.text
    assert "microvascular" in document.text
    assert "临床指南" not in document.text
    action_types = {action.action_type for action in document.cleaning_actions}
    assert {"remove_header", "remove_page_number", "repair_ocr_numeric_unit", "repair_hyphenation"}.issubset(action_types)
    assert document.quality_report is None
    assert sum(action.action_type == "remove_header" for action in document.cleaning_actions) == 2


def test_consecutive_tables_with_same_schema_are_merged_and_chunked_as_table():
    first = ParsedTable("t1", "剂量", 1, 1, [], ["药物", "剂量"], [["A", "5 mg"]], [], [], "old-1", "native", 0.96)
    second = ParsedTable("t2", None, 2, 2, [], ["药物", "剂量"], [["B", "10 mg"]], [], [], "old-2", "native", 0.94)
    document = ParsedDocument("table.pdf", "pdf", "v2", [
        ParsedPage(1, "", "native", tables=[first]),
        ParsedPage(2, "", "native", tables=[second]),
    ])

    clean_preserving_structure(document)
    chunks = StructuralSplitter(child_tokens=80, parent_tokens=120).split(document)

    assert first.page_end == 2
    assert first.rows == [["A", "5 mg"], ["B", "10 mg"]]
    assert document.pages[1].tables == []
    assert any(action.action_type == "merge_cross_page_table" for action in document.cleaning_actions)
    assert any(chunk.metadata["content_type"] == "table" for chunk in chunks)


def test_low_confidence_ocr_is_cleaned_without_quality_gate():
    page = ParsedPage(
        1, "???", "ocr", ocr_confidence=0.15,
        blocks=[TextBlock("???", confidence=0.15, extraction_method="ocr", block_id="p1_b1")],
    )
    document = clean_preserving_structure(ParsedDocument("bad.pdf", "pdf", "v2", [page]))
    chunks = StructuralSplitter(child_tokens=80, parent_tokens=120).split(document)
    assert page.quality_score is None
    assert page.quality_status == "not_evaluated"
    assert document.quality_report is None
    assert any(chunk.chunk_type == "child" for chunk in chunks)


def test_page_classifier_detects_multicolumn_layout():
    pdf = fitz.open()
    page = pdf.new_page(width=600, height=800)
    blocks = [
        TextBlock("左栏医学内容 " * 8, bbox=(30, 70, 220, 130)),
        TextBlock("左栏随访内容 " * 8, bbox=(30, 180, 220, 240)),
        TextBlock("右栏治疗内容 " * 8, bbox=(380, 70, 570, 130)),
        TextBlock("右栏剂量内容 " * 8, bbox=(380, 180, 570, 240)),
    ]
    classification = classify_page(page, blocks, 0)
    pdf.close()
    assert classification.page_type == "complex_layout"
    assert classification.extraction_mode == "embedded_only"


def test_executor_overwrites_untrusted_identity_context_and_caches():
    implementation = _Implementation()
    executor = _executor("qa_context_cache_v2", implementation)
    payload = {
        "value": "dose",
        "context": {"request_id": "attacker", "user_id": 999, "tenant_id": 999, "authorized_kb_ids": [999]},
    }

    first, digest = executor.execute("qa_context_cache_v2", payload, _runtime())
    second, second_digest = executor.execute("qa_context_cache_v2", payload, _runtime())

    assert first.status == "success" and second.status == "success"
    assert digest == second_digest and second.usage.cache_hit
    assert len(implementation.inputs) == 1
    assert implementation.inputs[0].context.user_id == 7
    assert implementation.inputs[0].context.tenant_id == 9
    assert implementation.inputs[0].context.authorized_kb_ids == [11]


def test_policy_blocks_unauthorized_agent_and_emergency_retrieval():
    implementation = _Implementation()
    executor = _executor("qa_policy_v2", implementation)

    unauthorized, _ = executor.execute("qa_policy_v2", {"value": "x"}, _runtime(agent_name="supervisor"))
    emergency, _ = executor.execute("qa_policy_v2", {"value": "x"}, _runtime(risk_level="emergency"))

    assert unauthorized.status == "forbidden"
    assert emergency.status == "forbidden"
    assert implementation.inputs == []


def test_executor_retries_retryable_error_then_succeeds():
    implementation = _Implementation(outcomes=[
        ToolResult(status="error", error=ToolError(code="TRANSIENT", message="retry", retryable=True)),
        ToolResult(status="success", data=["ok"]),
    ])
    executor = _executor("qa_retry_v2", implementation, max_retries=1)
    result, _ = executor.execute("qa_retry_v2", {"value": "x"}, _runtime())
    assert result.status == "success"
    assert result.usage.retries == 1
    assert len(implementation.inputs) == 2


def test_executor_timeout_and_circuit_breaker(monkeypatch):
    monkeypatch.setattr(settings, "TOOL_CIRCUIT_FAILURE_THRESHOLD", 2)
    timeout_impl = _Implementation(delay=0.04)
    timeout_executor = _executor("qa_timeout_v2", timeout_impl, timeout_seconds=0.005, max_retries=0, cache_ttl_seconds=None)
    timeout, _ = timeout_executor.execute("qa_timeout_v2", {"value": "x"}, _runtime())
    assert timeout.status == "timeout"
    assert timeout.error and timeout.error.code == "TOOL_TIMEOUT"

    failing = _Implementation(outcomes=[RuntimeError("one"), RuntimeError("two"), ToolResult(status="success")])
    breaker = _executor("qa_circuit_v2", failing, max_retries=0, cache_ttl_seconds=None)
    assert breaker.execute("qa_circuit_v2", {"value": "x"}, _runtime())[0].status == "error"
    assert breaker.execute("qa_circuit_v2", {"value": "y"}, _runtime())[0].status == "error"
    blocked, _ = breaker.execute("qa_circuit_v2", {"value": "z"}, _runtime())
    assert blocked.error and blocked.error.code == "TOOL_CIRCUIT_OPEN"
    assert len(failing.inputs) == 2
