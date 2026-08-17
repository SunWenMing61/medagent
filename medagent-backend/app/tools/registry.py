"""Explicit, versioned tool catalog with agent/scope/risk metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    version: str
    input_schema: type
    output_schema: type | None = None
    description: str = "Read-only application capability with validated inputs and normalized output."
    category: Literal["retrieval", "web_source", "medical_source", "memory", "document", "workflow", "safety"] = "retrieval"
    read_only: bool = True
    has_side_effect: bool = False
    idempotent: bool = True
    risk_level: Literal["low", "medium", "high"] = "low"
    requires_approval: bool = False
    allowed_agents: frozenset[str] = field(default_factory=lambda: frozenset({"*"}))
    required_scopes: frozenset[str] = field(default_factory=frozenset)
    timeout_seconds: float = 8.0
    max_retries: int = 1
    max_calls_per_run: int = 5
    cache_ttl_seconds: int | None = 60
    fallback_tool: str | None = None


class ToolRegistry:
    def __init__(self) -> None:
        self._items: dict[str, tuple[ToolDefinition, Any]] = {}
        self._enabled: dict[str, bool] = {}

    def register(self, definition: ToolDefinition, implementation: Any) -> None:
        if definition.name in self._items:
            raise ValueError(f"Tool already registered: {definition.name}")
        self._items[definition.name] = (definition, implementation)
        self._enabled[definition.name] = True

    def get(self, name: str, version: str | None = None) -> tuple[ToolDefinition, Any]:
        try:
            definition, implementation = self._items[name]
        except KeyError as exc:
            raise KeyError(f"Tool is not whitelisted: {name}") from exc
        if version and definition.version != version:
            raise KeyError(f"Tool version is not registered: {name}@{version}")
        if not self._enabled.get(name, False):
            raise KeyError(f"Tool is disabled: {name}")
        return definition, implementation

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name not in self._items:
            raise KeyError(name)
        self._enabled[name] = bool(enabled)

    def is_enabled(self, name: str) -> bool:
        return bool(self._enabled.get(name, False))

    def definitions(self, *, include_disabled: bool = False) -> list[ToolDefinition]:
        return [
            item[0]
            for name, item in self._items.items()
            if include_disabled or self._enabled.get(name, False)
        ]

    def available(self, *, agent_name: str, permission_scopes: set[str], category: str | None = None, limit: int = 4) -> list[ToolDefinition]:
        result = []
        for definition in self.definitions():
            if category and definition.category != category:
                continue
            if "*" not in definition.allowed_agents and agent_name not in definition.allowed_agents:
                continue
            if not set(definition.required_scopes).issubset(permission_scopes):
                continue
            result.append(definition)
        return result[: max(0, min(limit, 4))]


tool_registry = ToolRegistry()
