from typing import Optional

HIGH_RISK_KEYWORDS = [
    "chest pain", "difficulty breathing", "shortness of breath", "unconscious",
    "massive bleeding", "severe allergy", "anaphylaxis", "severe headache",
    "seizure", "convulsion", "suicide", "self-harm", "高烧", "抽搐",
    "胸痛", "呼吸困难", "意识不清", "大量出血", "严重过敏",
    "剧烈头痛", "自伤", "自杀", "儿童高热",
]

MEDICAL_BOUNDARY_KEYWORDS = [
    "diagnosis", "prescribe", "prescription", "stop medication",
    "change medication", "adjust dosage", "诊断", "处方",
    "开药", "停药", "换药", "调整剂量",
]


class SafetyService:
    @staticmethod
    def check_high_risk(question: str) -> tuple:
        """
        Check if question contains high-risk keywords.
        Returns (is_high_risk: bool, matched_keywords: list)
        """
        q_lower = question.lower()
        matched = []
        for kw in HIGH_RISK_KEYWORDS:
            if kw.lower() in q_lower:
                matched.append(kw)
        return len(matched) > 0, matched

    @staticmethod
    def check_medical_boundary(question: str) -> tuple:
        """
        Check if question asks for medical boundary violations.
        Returns (is_boundary_violation: bool, matched_keywords: list)
        """
        q_lower = question.lower()
        matched = []
        for kw in MEDICAL_BOUNDARY_KEYWORDS:
            if kw.lower() in q_lower:
                matched.append(kw)
        return len(matched) > 0, matched

    @staticmethod
    def get_high_risk_response(matched_keywords: list) -> str:
        keywords = ", ".join(matched_keywords[:5])
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
        keywords = ", ".join(matched_keywords[:5])
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
        return (
            "**Medical Disclaimer:** This information is for reference and educational purposes only. "
            "It does not constitute medical advice, diagnosis, or treatment. "
            "Always consult a qualified healthcare provider with any questions about your health."
        )


safety_service = SafetyService()
