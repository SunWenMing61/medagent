import pytest

from app.core.config import settings


@pytest.fixture(autouse=True)
def disable_live_answer_model_calls(monkeypatch):
    """Tests never spend model quota unless they explicitly opt in with a fake client."""
    monkeypatch.setattr(settings, "LLM_ANSWER_GENERATION_ENABLED", False)
    monkeypatch.setattr(settings, "PDF_VISION_ANALYSIS_ENABLED", False)
