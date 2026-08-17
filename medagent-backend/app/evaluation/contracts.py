"""Typed contracts shared by dataset loaders, evaluators and the runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class EvaluationResult:
    evaluator_name: str
    metric_name: str
    score: float
    passed: bool
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CaseExecution:
    output: str
    status: str = "success"
    agent_steps: list[dict[str, Any]] = field(default_factory=list)
    routing_history: list[str] = field(default_factory=list)
    retrievals: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    llm_calls: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
