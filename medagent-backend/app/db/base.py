from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base for PostgreSQL models (with pgvector support)."""
    pass


class MySQLBase(DeclarativeBase):
    """Base for MySQL models (relational data)."""
    pass
