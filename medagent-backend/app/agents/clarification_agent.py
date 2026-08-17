"""Medical clarification agent limited to one to three high-value questions."""

from app.agents.registry import AgentDefinition, agent_registry
from app.agents.schemas import ClarificationResult, InputTriageResult


VERSION = "1.0.0"


class MedicalClarificationAgent:
    name = "medical_clarification"
    version = VERSION

    def run(self, triage: InputTriageResult) -> ClarificationResult:
        topics = triage.clarification_topics[:3]
        question_map = {
            "症状开始方式": "症状是突然出现还是逐渐出现的？",
            "持续时间和严重程度": "症状持续了多久，目前严重程度如何？",
            "伴随的危险症状": "是否伴有意识异常、肢体无力、呼吸困难或大量出血？",
        }
        questions = [question_map.get(item, f"请补充：{item}？") for item in topics]
        return ClarificationResult(
            need_clarification=bool(triage.need_clarification and questions),
            missing_fields=topics,
            priority=topics,
            questions=questions,
            reason="Only the most safety-relevant missing details are requested.",
        )


clarification_agent = MedicalClarificationAgent()
agent_registry.register(
    AgentDefinition(
        name=clarification_agent.name,
        version=VERSION,
        prompt_id="medical_clarification",
        prompt_version="clarification_v1",
        output_schema=ClarificationResult,
        model_setting="TRIAGE_MODEL",
    ),
    clarification_agent,
)
