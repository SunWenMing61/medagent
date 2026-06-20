"""Tests for utility functions."""

import pytest

from app.utils.text_splitter import split_text


class TestTextSplitter:
    def test_split_empty(self):
        assert split_text("") == []

    def test_split_short(self):
        result = split_text("Hello world", chunk_size=500)
        assert len(result) == 1
        assert result[0] == "Hello world"

    def test_split_long(self):
        text = "。".join(["A" * 100] * 10)
        result = split_text(text, chunk_size=200, chunk_overlap=20)
        assert len(result) > 1

    def test_split_boundary(self):
        text = "第一段内容。第二段内容。第三段内容。"
        result = split_text(text, chunk_size=10, chunk_overlap=2)
        assert len(result) >= 3


class TestSafetyService:
    def test_high_risk_keywords(self):
        from app.services.safety_service import SafetyService
        is_high, matched = SafetyService.check_high_risk("我胸痛")
        assert is_high
        assert "胸痛" in matched

    def test_safe_question(self):
        from app.services.safety_service import SafetyService
        is_high, matched = SafetyService.check_high_risk("什么是高血压？")
        assert not is_high

    def test_boundary_detection(self):
        from app.services.safety_service import SafetyService
        is_boundary, matched = SafetyService.check_medical_boundary("请给我开药")
        assert is_boundary
        assert "开药" in matched


class TestVectorService:
    def test_search_no_kb(self):
        from app.services.vector_service import vector_service
        try:
            results = vector_service.search(
                query="test query",
                kb_ids=None,
                top_k=1,
                threshold=0.0,
            )
            assert isinstance(results, list)
        except Exception as e:
            # May fail without DB/API key, but should handle gracefully
            assert "API" in str(e) or "connect" in str(e).lower()
