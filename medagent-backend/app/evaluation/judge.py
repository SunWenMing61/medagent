"""Configurable structured-output judge for non-deterministic assertions."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field


class JudgeOutput(BaseModel):
    score: float = Field(ge=0, le=1)
    passed: bool
    reason: str
    evidence: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


class StructuredJudgeClient(Protocol):
    async def parse(self, *, model: str, prompt: str, response_model: type[JudgeOutput]) -> JudgeOutput: ...


class LLMJudge:
    def __init__(self, client: StructuredJudgeClient, *, model: str, prompt_version: str):
        self.client, self.model, self.prompt_version = client, model, prompt_version

    async def evaluate(self, *, rubric: str, case: dict[str, Any], output: str, evidence: list[dict[str, Any]]) -> JudgeOutput:
        prompt = f"judge_prompt_version={self.prompt_version}\nReturn only the declared structured schema. Do not infer patient facts.\nRubric: {rubric}\nCase: {case}\nOutput: {output}\nEvidence: {evidence}"
        return await self.client.parse(model=self.model, prompt=prompt, response_model=JudgeOutput)
