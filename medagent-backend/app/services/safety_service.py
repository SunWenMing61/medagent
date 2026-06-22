# 导入 Optional 类型,用于表示可能为 None 的返回值
from typing import Optional

# 高风险关键词列表:包含可能表明紧急医疗状况的词语(中英文)
HIGH_RISK_KEYWORDS = [
    "chest pain", "difficulty breathing", "shortness of breath", "unconscious",
    "massive bleeding", "severe allergy", "anaphylaxis", "severe headache",
    "seizure", "convulsion", "suicide", "self-harm", "高烧", "抽搐",
    "胸痛", "呼吸困难", "意识不清", "大量出血", "严重过敏",
    "剧烈头痛", "自伤", "自杀", "儿童高热",
]

# 医疗边界关键词列表:涉及诊断、处方等超出系统能力范围的行为(中英文)
MEDICAL_BOUNDARY_KEYWORDS = [
    "diagnosis", "prescribe", "prescription", "stop medication",
    "change medication", "adjust dosage", "诊断", "处方",
    "开药", "停药", "换药", "调整剂量",
]


class SafetyService:
    """安全审查服务,负责检测用户输入中的高风险和越界医疗请求。"""

    @staticmethod
    def check_high_risk(question: str) -> tuple:
        """
        检查用户问题是否包含高风险关键词(可能表示紧急医疗状况)。

        Args:
            question: 用户输入的文本

        Returns:
            (is_high_risk: bool, matched_keywords: list) 元组,
            分别表示是否高风险和匹配到的关键词列表
        """
        q_lower = question.lower()  # 转为小写以进行不区分大小写的匹配
        matched = []  # 存储匹配到的关键词
        for kw in HIGH_RISK_KEYWORDS:
            if kw.lower() in q_lower:  # 将关键词也转为小写进行比较
                matched.append(kw)      # 记录匹配的关键词
        return len(matched) > 0, matched  # 返回是否匹配及匹配列表

    @staticmethod
    def check_medical_boundary(question: str) -> tuple:
        """
        检查用户问题是否涉及医疗越界行为(诊断、处方等)。

        Args:
            question: 用户输入的文本

        Returns:
            (is_boundary_violation: bool, matched_keywords: list) 元组,
            分别表示是否越界和匹配到的关键词列表
        """
        q_lower = question.lower()  # 转为小写
        matched = []  # 存储匹配到的关键词
        for kw in MEDICAL_BOUNDARY_KEYWORDS:
            if kw.lower() in q_lower:  # 不区分大小写的包含检查
                matched.append(kw)
        return len(matched) > 0, matched

    @staticmethod
    def get_high_risk_response(matched_keywords: list) -> str:
        """生成高风险警报的回复消息,引导用户立即寻求专业医疗帮助。

        Args:
            matched_keywords: 匹配到的高风险关键词列表

        Returns:
            格式化的安全提示信息字符串
        """
        keywords = ", ".join(matched_keywords[:5])  # 取前 5 个关键词,用逗号连接
        return (
            f"⚠️ **Important Safety Notice**\n\n"
            f"Your question contains keywords that may indicate an urgent medical situation: **{keywords}**.\n\n"
            f"🚨 **Please seek immediate medical attention:**\n"
            f"- Call emergency services (120 in China, 911 in US) immediately\n"
            f"- Go to the nearest emergency room\n"
            f"- Do not wait for an online response\n\n"
            f"This system cannot provide emergency medical advice. "
            f"Please consult a qualified healthcare professional for any medical concerns."
        )

    @staticmethod
    def get_boundary_response(matched_keywords: list) -> str:
        """生成医疗边界提示的回复消息,说明系统不能做什么。

        Args:
            matched_keywords: 匹配到的越界关键词列表

        Returns:
            格式化的边界提示信息字符串
        """
        keywords = ", ".join(matched_keywords[:5])  # 取前 5 个关键词
        return (
            f"⚠️ **Notice**\n\n"
            f"Your question involves: **{keywords}**.\n\n"
            f"This system is designed for medical knowledge reference only and cannot:\n"
            f"- Provide a diagnosis\n"
            f"- Generate a prescription\n"
            f"- Advise on stopping, changing, or adjusting medication dosage\n"
            f"- Replace professional medical advice\n\n"
            f"Please consult a qualified doctor or pharmacist for personalized medical decisions. "
            f"Your health decisions should always be made in consultation with a healthcare professional."
        )

    @staticmethod
    def get_disclaimer() -> str:
        """获取标准的医疗免责声明文本。"""
        return (
            "**Medical Disclaimer:** This information is for reference and educational purposes only. "
            "It does not constitute medical advice, diagnosis, or treatment. "
            "Always consult a qualified healthcare provider with any questions about your health."
        )


# 全局单例实例,供其他模块直接使用
safety_service = SafetyService()
