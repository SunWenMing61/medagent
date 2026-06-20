"""Database session management.

Includes a monkey-patch for psycopg2 to handle Windows locale encoding issues
where the system locale (e.g., zh_CN/CP936) causes UnicodeDecodeError in
psycopg2's C extension when connecting to PostgreSQL.
"""
import logging
from functools import wraps

logger = logging.getLogger(__name__)

# Workaround for psycopg2 UnicodeDecodeError on Windows with Chinese locale.
# Set locale environment variables BEFORE libpq is loaded (first psycopg2 import).
# This ensures libpq uses UTF-8 for internal string encoding rather than CP936.
import os as _os
if _os.name == "nt":
    _os.environ.setdefault("LANG", "en_US.UTF-8")
    _os.environ.setdefault("LC_CTYPE", "en_US.UTF-8")
    _os.environ.setdefault("PGCLIENTENCODING", "UTF8")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings

# ==================== PostgreSQL (pgvector for vector search) ====================
pg_engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"client_encoding": "utf8"},
)
PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)


def get_pg_db():
    """Dependency that provides a PostgreSQL session."""
    db: Session = PgSessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== MySQL (relational data) ====================
mysql_engine = create_engine(settings.MYSQL_DATABASE_URL, pool_pre_ping=True)
MySQLSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=mysql_engine)


def get_mysql_db():
    """Dependency that provides a MySQL session."""
    db: Session = MySQLSessionLocal()
    try:
        yield db
    finally:
        db.close()
