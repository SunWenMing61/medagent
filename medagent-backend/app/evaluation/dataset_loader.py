"""Load versioned JSON/JSONL golden datasets into one normalized contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class DatasetLoader:
    def load(self, path: str | Path) -> list[dict[str, Any]]:
        source = Path(path)
        if source.suffix.lower() == ".jsonl":
            return [json.loads(line) for line in source.read_text(encoding="utf-8").splitlines() if line.strip()]
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return payload
        for key in ("cases", "retrieval", "data"):
            if isinstance(payload.get(key), list):
                return payload[key]
        raise ValueError(f"Unsupported dataset shape: {source}")

    @staticmethod
    def validate(case: dict[str, Any]) -> None:
        if not str(case.get("id", "")).strip():
            raise ValueError("Evaluation case requires a stable id")


dataset_loader = DatasetLoader()
