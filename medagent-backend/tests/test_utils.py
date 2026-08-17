"""工具函数测试。"""

# 导入 pytest 测试框架
# 导入文本分割工具函数
from app.utils.text_splitter import split_text


# 文本分割器测试类
class TestTextSplitter:
    """测试文本切分功能的正确性。"""

    def test_split_empty(self):
        """测试空字符串的分割：预期返回空列表。"""
        assert split_text("") == []

    def test_split_short(self):
        """测试短文本的分割：文本长度小于 chunk_size，应返回包含原文本的列表。"""
        result = split_text("Hello world", chunk_size=500)
        assert len(result) == 1
        assert result[0] == "Hello world"

    def test_split_long(self):
        """测试长文本的分割：文本长度超过 chunk_size，应返回多个切片。"""
        # 构造一个包含 10 段的长文本
        text = "。".join(["A" * 100] * 10)
        result = split_text(text, chunk_size=200, chunk_overlap=20)
        # 预期结果中包含多个切片
        assert len(result) > 1

    def test_split_boundary(self):
        """测试边界分割：使用较小 chunk_size 确保正确按边界切分中文文本。"""
        text = "第一段内容。第二段内容。第三段内容。"
        result = split_text(text, chunk_size=10, chunk_overlap=2)
        # 预期的切片数量至少为 3
        assert len(result) >= 3


# 安全服务测试类
class TestSafetyService:
    """测试医疗安全检测服务的功能。"""

    def test_high_risk_keywords(self):
        """测试高风险关键词检测：包含"胸痛"等紧急关键词应触发高风险标记。"""
        from app.services.safety_service import SafetyService
        is_high, matched = SafetyService.check_high_risk("我胸痛")
        # 预期为高风险
        assert is_high
        # 预期匹配到"胸痛"关键词
        assert "胸痛" in matched

    def test_safe_question(self):
        """测试安全问题的检测：普通医学问题不应触发高风险标记。"""
        from app.services.safety_service import SafetyService
        is_high, matched = SafetyService.check_high_risk("什么是高血压？")
        # 预期不是高风险
        assert not is_high

    def test_boundary_detection(self):
        """测试医疗边界检测：包含"开药"等操作应触发边界警告。"""
        from app.services.safety_service import SafetyService
        is_boundary, matched = SafetyService.check_medical_boundary("请给我开药")
        # 预期触发边界警告
        assert is_boundary
        # 预期匹配到"开药"关键词
        assert "开药" in matched
