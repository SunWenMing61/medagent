"""Conservative medical-risk triage and generated-output policy."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class RiskLevel(str, Enum):
    ROUTINE = "routine"
    CAUTION = "caution"
    URGENT = "urgent"
    EMERGENCY = "emergency"
    SELF_HARM = "self_harm"


@dataclass(slots=True)
class RiskAssessment:
    level: RiskLevel
    matched: list[str]


_SELF_HARM = [r"suicid", r"self[- ]?harm", r"kill myself", r"自杀", r"自伤", r"不想活"]
_EMERGENCY = [
    r"chest pain", r"胸痛", r"difficulty breathing", r"shortness of breath", r"呼吸困难",
    r"unconscious", r"意识不清", r"massive bleeding", r"大量出血", r"anaphylaxis",
    r"严重过敏", r"seizure", r"convulsion", r"抽搐", r"sudden.*severe headache",
    r"worst headache", r"突发.*剧烈头痛",
]
_URGENT = [r"high fever", r"高烧", r"儿童高热", r"persistent vomiting", r"持续呕吐"]
_BOUNDARY = [
    r"diagnos", r"prescri", r"stop (taking|your medication)", r"adjust (your )?dosage",
    r"诊断", r"处方", r"开药", r"停药", r"换药", r"调整剂量",
]
_UNSAFE_OUTPUT = [
    r"\bdiagnosis\s*[:：]", r"诊断\s*[:：]", r"\bprescri(?:be|ption)\b",
    r"\byou (definitely )?have\b", r"\btake \d+(?:\.\d+)?\s*(?:mg|ml)\b",
    r"\bstop taking\b", r"\bdiscontinue\b", r"\badjust your dosage\b",
    r"你(患有|就是).{0,20}(病|症)", r"每天服用\s*\d+", r"立即停药", r"自行调整剂量",
]


class SafetyService:
    @staticmethod
    def assess(question: str) -> RiskAssessment:
        value = question or ""
        for level, patterns in (
            (RiskLevel.SELF_HARM, _SELF_HARM),
            (RiskLevel.EMERGENCY, _EMERGENCY),
            (RiskLevel.URGENT, _URGENT),
        ):
            matched = [pattern for pattern in patterns if re.search(pattern, value, re.IGNORECASE)]
            if matched:
                return RiskAssessment(level, matched)
        return RiskAssessment(RiskLevel.ROUTINE, [])

    @staticmethod
    def check_high_risk(question: str) -> tuple[bool, list[str]]:
        assessment = SafetyService.assess(question)
        return assessment.level in {RiskLevel.URGENT, RiskLevel.EMERGENCY, RiskLevel.SELF_HARM}, assessment.matched

    @staticmethod
    def check_medical_boundary(question: str) -> tuple[bool, list[str]]:
        matched = [pattern for pattern in _BOUNDARY if re.search(pattern, question or "", re.IGNORECASE)]
        return bool(matched), matched

    @staticmethod
    def check_output(answer: str) -> list[str]:
        return [pattern for pattern in _UNSAFE_OUTPUT if re.search(pattern, answer or "", re.IGNORECASE)]

    @staticmethod
    def get_high_risk_response(matched_keywords: list[str], level: RiskLevel | None = None) -> str:
        risk = level or RiskLevel.EMERGENCY
        if risk == RiskLevel.SELF_HARM:
            return (
                "⚠️ **安全提醒**\n\n如果你可能伤害自己，请现在联系所在地的紧急服务或危机干预热线，"
                "并尽快告诉一位可信任、能陪在你身边的人。请远离可能造成伤害的物品，不要独自承受。"
                "本系统不能提供危机干预。"
            )
        return (
            "⚠️ **可能需要紧急医疗帮助 / Immediate emergency attention may be needed**\n\n"
            "你描述的情况可能具有紧急性。请立即联系所在地的紧急医疗服务，或尽快前往最近的急诊。"
            "如可能，请让他人陪同；不要为了等待在线回答而延误就医。"
            "本系统无法判断病情，也不能替代现场医疗评估。"
        )

    @staticmethod
    def get_boundary_response(matched_keywords: list[str]) -> str:
        del matched_keywords
        return (
            "⚠️ **医疗安全边界**\n\n本系统不能做出个人诊断、开具处方，或建议自行停药、换药和调整剂量。"
            "请让医生或药师结合病史、检查结果和当前用药进行个体化判断。"
        )

    @staticmethod
    def get_disclaimer() -> str:
        return (
            "**医疗免责声明 / Medical Disclaimer：** 本信息仅用于参考和健康教育，不构成医疗建议、诊断或治疗。"
            "有关个人健康与用药的决定，请咨询合格的医疗专业人员。"
        )


safety_service = SafetyService()
