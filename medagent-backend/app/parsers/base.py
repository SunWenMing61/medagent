"""Parser interface shared by local and future online-source adapters."""

from __future__ import annotations

from typing import Callable, Protocol

from app.parsers.models import ParsedDocument


ParseProgress = Callable[[int, int, bool], None]


class DocumentParser(Protocol):
    version: str

    def parse(self, file_path: str, progress_callback: ParseProgress | None = None) -> ParsedDocument:
        ...
