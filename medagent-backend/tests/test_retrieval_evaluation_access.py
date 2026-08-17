from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.v1.retrieval_debug import hybrid_retrieval_comparison


def test_medical_rag_evaluation_rejects_non_admin_user():
    with pytest.raises(HTTPException) as exc_info:
        hybrid_retrieval_comparison(current_user=SimpleNamespace(role="user"))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Admin access required"


def test_medical_rag_evaluation_allows_admin_user():
    expected = {"schema_version": "medical-retrieval-benchmark-v3"}
    with patch(
        "app.api.v1.retrieval_debug.run_hybrid_retrieval_comparison",
        return_value=expected,
    ):
        result = hybrid_retrieval_comparison(current_user=SimpleNamespace(role="admin"))

    assert result == expected
