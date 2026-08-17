"""Compatibility entry point for schema initialization.

Schema creation and upgrades are exclusively owned by Alembic. This module is
kept so old operational scripts fail forward into the supported migration path
instead of calling SQLAlchemy ``create_all`` or destructive ``drop_all``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def init_database() -> None:
    """Upgrade PostgreSQL and MySQL schemas to the current Alembic head."""

    for database in ("postgres", "mysql"):
        subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-x",
                f"database={database}",
                "upgrade",
                "head",
            ],
            cwd=BACKEND_ROOT,
            check=True,
        )


def drop_database() -> None:
    """Refuse the legacy destructive operation."""

    raise RuntimeError(
        "Automatic database deletion is disabled. Follow the documented, "
        "environment-specific rollback procedure instead."
    )


if __name__ == "__main__":
    if "--drop" in sys.argv:
        drop_database()
    init_database()
