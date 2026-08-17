"""Deterministic token counting with a dependency-free fallback."""

from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"[\u3400-\u9fff]|[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)?|[^\s]")


def count_tokens(text: str) -> int:
    return len(token_units(text))


def token_units(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text)
