"""Deterministic structure-first, semantic-aware parent/child chunking."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.chunking.models import ChunkDraft
from app.chunking.token_counter import count_tokens, token_units
from app.parsers.models import ParsedDocument, TextBlock


CHUNKER_VERSION = "hybrid-structural-semantic-v3"
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。！？!?；;])\s*|(?<=\.)\s+|\n+")
_LATIN_TERM = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)?", re.I)
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")


@dataclass(slots=True)
class _Section:
    page: int
    page_end: int
    ordinal: int
    path: list[str]
    text: str
    block_ids: list[str]
    content_type: str = "paragraph"
    extraction_method: str = "native"
    quality_status: str = "not_evaluated"
    ocr_confidence: float | None = None


@dataclass(slots=True)
class _SemanticUnit:
    text: str
    paragraph_start: bool = False


class StructuralSplitter:
    version = CHUNKER_VERSION

    def __init__(self, child_tokens: int = 320, parent_tokens: int = 900, overlap_tokens: int = 48):
        if child_tokens <= 0 or parent_tokens < child_tokens or overlap_tokens < 0:
            raise ValueError("Invalid chunk token limits")
        self.child_tokens = child_tokens
        self.parent_tokens = parent_tokens
        self.overlap_tokens = min(overlap_tokens, child_tokens // 2)

    def split(self, document: ParsedDocument) -> list[ChunkDraft]:
        sections = self._sections(document)
        drafts: list[ChunkDraft] = []
        for section in sections:
            parent_texts = self._pack_content(section.text, self.parent_tokens, 0, section.content_type)
            for parent_text in parent_texts:
                parent_id = self._id(document, section, "parent", parent_text)
                drafts.append(self._draft(parent_id, parent_text, len(drafts), "parent", section, None))
                for child_text in self._pack_content(parent_text, self.child_tokens, self.overlap_tokens, section.content_type):
                    child_id = self._id(document, section, "child", child_text)
                    drafts.append(
                        self._draft(child_id, child_text, len(drafts), "child", section, parent_id)
                    )
        return drafts

    def _sections(self, document: ParsedDocument) -> list[_Section]:
        result: list[_Section] = []
        ordinal = 0
        heading_path: list[str] = []
        for page in document.pages:
            buffer: list[str] = []
            block_ids: list[str] = []
            current_type = "paragraph"

            def flush() -> None:
                nonlocal ordinal, buffer, block_ids
                if buffer:
                    result.append(_Section(
                        page.page_number, page.page_number, ordinal, heading_path.copy(),
                        "\n".join(buffer), block_ids.copy(), current_type,
                        page.extraction_method, page.quality_status, page.ocr_confidence,
                    ))
                    ordinal += 1
                    buffer, block_ids = [], []

            for block in page.blocks or [TextBlock(page.text)]:
                is_heading = block.kind == "heading" or bool(re.match(r"^#{1,6}\s+", block.text))
                if is_heading:
                    flush()
                    title = re.sub(r"^#{1,6}\s+", "", block.text).strip()
                    level_match = re.match(r"^(\d+(?:\.\d+)*)", title)
                    level = level_match.group(1).count(".") + 1 if level_match else 1
                    if title:
                        heading_path = heading_path[:level - 1] + [title]
                else:
                    # Empty image placeholders are not searchable. A figure block
                    # carrying a grounded visual description must be embedded.
                    if not block.text:
                        continue
                    block_type = {
                        "list": "list", "table": "table", "caption": "caption",
                        "figure": "figure",
                        "footnote": "footnote", "reference": "reference",
                    }.get(block.kind, "paragraph")
                    if buffer and block_type != current_type:
                        flush()
                    current_type = block_type
                    buffer.append(block.text)
                    block_ids.append(block.block_id or f"p{page.page_number}_b{block.order}")
            flush()
        return [section for section in result if section.text.strip()]

    @classmethod
    def _pack_content(cls, text: str, limit: int, overlap: int, content_type: str) -> list[str]:
        if content_type == "table":
            return cls._pack_table(text, limit)
        if content_type in {"list", "figure", "caption", "footnote", "reference"}:
            return cls._pack_lines(text, limit)
        return cls._pack(text, limit, overlap)

    @staticmethod
    def _pack_lines(text: str, limit: int) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        chunks: list[str] = []
        current: list[str] = []
        for line in lines:
            candidate = "\n".join(current + [line])
            if current and count_tokens(candidate) > limit:
                chunks.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            chunks.append("\n".join(current))
        return chunks

    @classmethod
    def _pack_table(cls, text: str, limit: int) -> list[str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) <= 2 or count_tokens(text) <= limit:
            return [text.strip()] if text.strip() else []
        header = lines[:2] if len(lines) >= 2 and set(lines[1].replace("|", "").replace("-", "").replace(":", "").strip()) == set() else []
        rows = lines[2:] if header else lines
        chunks: list[str] = []
        current = header.copy()
        for row in rows:
            candidate = "\n".join(current + [row])
            if len(current) > len(header) and count_tokens(candidate) > limit:
                chunks.append("\n".join(current))
                current = header.copy()
            current.append(row)
        if len(current) > len(header) or (header and not chunks):
            chunks.append("\n".join(current))
        return chunks

    @staticmethod
    def _pack(text: str, limit: int, overlap: int) -> list[str]:
        units = StructuralSplitter._semantic_units(text)
        if not units:
            return []

        expanded: list[_SemanticUnit] = []
        for unit in units:
            if count_tokens(unit.text) <= limit:
                expanded.append(unit)
                continue
            words = token_units(unit.text)
            step = max(1, limit - overlap)
            expanded.extend(
                _SemanticUnit(" ".join(words[start:start + limit]).strip(), unit.paragraph_start or start == 0)
                for start in range(0, len(words), step)
            )
        units = [unit for unit in expanded if unit.text]

        segments: list[list[_SemanticUnit]] = []
        start = 0
        minimum = max(1, int(limit * 0.42))
        target = max(minimum, int(limit * 0.78))
        while start < len(units):
            end = start
            used = 0
            while end < len(units) and used + count_tokens(units[end].text) <= limit:
                used += count_tokens(units[end].text)
                end += 1
            if end >= len(units):
                segments.append(units[start:])
                break
            if end == start:
                end = start + 1
            candidates: list[tuple[float, int]] = []
            running = 0
            for boundary in range(start + 1, end + 1):
                running += count_tokens(units[boundary - 1].text)
                if running < minimum:
                    continue
                cohesion = StructuralSplitter._boundary_cohesion(units, boundary)
                distance = abs(running - target) / max(target, 1)
                paragraph_bonus = 0.35 if boundary < len(units) and units[boundary].paragraph_start else 0.0
                candidates.append((cohesion + 0.12 * distance - paragraph_bonus, boundary))
            cut = min(candidates, key=lambda item: (item[0], -item[1]))[1] if candidates else end
            segments.append(units[start:cut])
            start = cut

        chunks: list[str] = []
        previous: list[_SemanticUnit] = []
        for segment in segments:
            prefix: list[_SemanticUnit] = []
            prefix_tokens = 0
            for unit in reversed(previous):
                size = count_tokens(unit.text)
                if prefix_tokens + size > overlap:
                    break
                prefix.insert(0, unit)
                prefix_tokens += size
            chosen = prefix + segment
            while prefix and count_tokens("\n".join(unit.text for unit in chosen)) > limit:
                prefix.pop(0)
                chosen = prefix + segment
            chunk = "\n".join(unit.text for unit in chosen).strip()
            if chunk:
                chunks.append(chunk)
            previous = segment
        return list(dict.fromkeys(chunks))

    @staticmethod
    def _semantic_units(text: str) -> list[_SemanticUnit]:
        units: list[_SemanticUnit] = []
        for paragraph_index, paragraph in enumerate(re.split(r"\n\s*\n", text)):
            sentences = [item.strip() for item in _SENTENCE_BOUNDARY.split(paragraph) if item.strip()]
            for index, sentence in enumerate(sentences):
                units.append(_SemanticUnit(sentence, paragraph_start=paragraph_index > 0 and index == 0))
        return units

    @staticmethod
    def _semantic_terms(text: str) -> set[str]:
        lowered = text.casefold()
        terms = set(_LATIN_TERM.findall(lowered))
        for run in _CJK_RUN.findall(lowered):
            if len(run) == 1:
                terms.add(run)
            else:
                terms.update(run[index:index + 2] for index in range(len(run) - 1))
        return terms

    @classmethod
    def _boundary_cohesion(cls, units: list[_SemanticUnit], boundary: int) -> float:
        left = cls._semantic_terms(" ".join(unit.text for unit in units[max(0, boundary - 2):boundary]))
        right = cls._semantic_terms(" ".join(unit.text for unit in units[boundary:boundary + 2]))
        return len(left & right) / len(left | right) if left or right else 0.0

    def _id(self, document: ParsedDocument, section: _Section, kind: str, text: str) -> str:
        source_hash = str(document.metadata.get("content_sha256", ""))
        raw = "\x1f".join([
            source_hash, document.parser_version, self.version, str(section.page),
            str(section.ordinal), "/".join(section.path), section.content_type, kind, text,
        ])
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _draft(logical_id: str, text: str, index: int, kind: str, section: _Section, parent: str | None) -> ChunkDraft:
        start_offset = section.text.find(text)
        return ChunkDraft(
            logical_id=logical_id,
            content=text,
            chunk_index=index,
            chunk_type=kind,  # type: ignore[arg-type]
            page_start=section.page,
            page_end=section.page_end,
            section_path=section.path,
            token_count=count_tokens(text),
            content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            parent_logical_id=parent,
            start_offset=max(0, start_offset),
            end_offset=max(0, start_offset) + len(text),
            metadata={
                "source_block_ids": section.block_ids,
                "content_type": section.content_type,
                "extraction_method": section.extraction_method,
                "quality_status": section.quality_status,
                "ocr_confidence": section.ocr_confidence,
                "chunking_strategy": "structure+semantic_cohesion+token_budget",
            },
        )
