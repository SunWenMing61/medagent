"""Typed chunk drafts before database IDs are assigned."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class ChunkDraft:
    logical_id: str
    content: str
    chunk_index: int
    chunk_type: Literal["parent", "child"]
    page_start: int
    page_end: int
    section_path: list[str]
    token_count: int
    content_sha256: str
    parent_logical_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
