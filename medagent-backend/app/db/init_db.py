"""Database initialization script for both PostgreSQL and MySQL."""
from app.db.base import Base, MySQLBase
from app.db.session import pg_engine, mysql_engine
from app.core.config import settings


def init_database():
    """Create all tables in both databases and initialize default data."""
    print(f"PostgreSQL: {settings.DATABASE_URL}")
    print("Creating PostgreSQL tables (document_chunk with pgvector)...")
    Base.metadata.create_all(bind=pg_engine)
    print("PostgreSQL tables created successfully!")

    print(f"MySQL: {settings.MYSQL_DATABASE_URL}")
    print("Creating MySQL tables (relational models)...")
    MySQLBase.metadata.create_all(bind=mysql_engine)
    print("MySQL tables created successfully!")


def drop_database():
    """Drop all tables from both databases (use with caution)."""
    print("Dropping PostgreSQL tables...")
    Base.metadata.drop_all(bind=pg_engine)
    print("PostgreSQL tables dropped!")

    print("Dropping MySQL tables...")
    MySQLBase.metadata.drop_all(bind=mysql_engine)
    print("MySQL tables dropped!")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--drop":
        drop_database()
    init_database()
