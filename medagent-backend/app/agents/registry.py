"""Explicit agent registry; agents never discover or call one another."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    name: str
    version: str
    prompt_id: str
    prompt_version: str
    output_schema: type
    model_setting: str
    uses_model: bool = False


class AgentRegistry:
    def __init__(self) -> None:
        self._items: dict[str, tuple[AgentDefinition, Any]] = {}

    def register(self, definition: AgentDefinition, implementation: Any) -> None:
        if definition.name in self._items:
            raise ValueError(f"Agent already registered: {definition.name}")
        self._items[definition.name] = (definition, implementation)

    def get(self, name: str) -> tuple[AgentDefinition, Any]:
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(f"Unknown or non-whitelisted agent: {name}") from exc

    def definitions(self) -> list[AgentDefinition]:
        return [item[0] for item in self._items.values()]


agent_registry = AgentRegistry()
