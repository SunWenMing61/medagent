"""Server-owned Assistant profiles for ordinary and memory-aware conversations."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class AssistantProfile:
    profile_id: str
    name: str
    description: str
    session_memory_enabled: bool
    long_term_memory_enabled: bool
    auto_web_search: bool
    intended_use: str


class AssistantProfileService:
    _profiles = {
        "general_qa": AssistantProfile(
            profile_id="general_qa",
            name="普通问答助手",
            description="自动识别问题类型：非医学问题直接由大模型回答，医学问题融合授权知识库与互联网证据。",
            session_memory_enabled=False,
            long_term_memory_enabled=False,
            auto_web_search=True,
            intended_use="通用大模型问答、医学知识库与联网联合检索",
        ),
        "memory_qa": AssistantProfile(
            profile_id="memory_qa",
            name="记忆问答助手",
            description="读取并更新持久化会话摘要，可在多轮医疗咨询中保持主题、实体和已确认约束。",
            session_memory_enabled=True,
            long_term_memory_enabled=True,
            auto_web_search=False,
            intended_use="多轮问诊、持续随访、复杂上下文",
        ),
    }

    def get(self, profile_id: str | None) -> AssistantProfile:
        return self._profiles.get(profile_id or "memory_qa", self._profiles["memory_qa"])

    def list(self) -> list[dict]:
        return [asdict(profile) for profile in self._profiles.values()]


assistant_profile_service = AssistantProfileService()
