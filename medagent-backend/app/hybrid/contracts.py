"""Public, privacy-safe contracts for hybrid routing and execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ExecutionMode(StrEnum):
    DIRECT = "DIRECT"
    REACT = "REACT"
    MULTI_AGENT = "MULTI_AGENT"
    REACT_ESCALATED_TO_MULTI_AGENT = "REACT_ESCALATED_TO_MULTI_AGENT"


class ComplexityLevel(StrEnum):
    VERY_SIMPLE = "VERY_SIMPLE"
    SIMPLE = "SIMPLE"
    MEDIUM = "MEDIUM"
    COMPLEX = "COMPLEX"
    VERY_COMPLEX = "VERY_COMPLEX"


@dataclass(slots=True)
class RouterDecision:
    execution_mode: ExecutionMode
    complexity_level: ComplexityLevel
    score: float
    confidence: float
    signals: dict[str, float] = field(default_factory=dict)
    decision_summary: str = ""
    latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    escalation_enabled: bool = False
    route_source: str = "rules"

    def as_dict(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode.value,
            "complexity_level": self.complexity_level.value,
            "score": self.score,
            "confidence": self.confidence,
            "signals": self.signals,
            "decision_summary": self.decision_summary,
            "latency_ms": self.latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "escalation_enabled": self.escalation_enabled,
            "route_source": self.route_source,
        }


class EscalationRequired(RuntimeError):
    def __init__(self, reason: str, state: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.state = state
