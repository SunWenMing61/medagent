"""Fail-fast checks for schema revisions required by runtime code."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.main import EXPECTED_SCHEMA_REVISION, _verify_migrations


def _engine_with_revision(revision):
    engine = MagicMock()
    connection = MagicMock()
    connection.execute.return_value.scalar_one_or_none.return_value = revision

    @contextmanager
    def connect():
        yield connection

    engine.connect.side_effect = connect
    return engine


def test_migration_guard_accepts_both_databases_at_required_head():
    engine = _engine_with_revision(EXPECTED_SCHEMA_REVISION)
    with (
        patch("app.main.settings.REQUIRE_MIGRATIONS", True),
        patch("app.main.pg_engine", engine),
        patch("app.main.mysql_engine", engine),
    ):
        _verify_migrations()


def test_migration_guard_rejects_outdated_schema_before_chat_requests():
    old = _engine_with_revision("0007_pairwise_answer_preferences")
    current = _engine_with_revision(EXPECTED_SCHEMA_REVISION)
    with (
        patch("app.main.settings.REQUIRE_MIGRATIONS", True),
        patch("app.main.pg_engine", current),
        patch("app.main.mysql_engine", old),
    ):
        with pytest.raises(RuntimeError, match=f"expected {EXPECTED_SCHEMA_REVISION}"):
            _verify_migrations()
