"""Alembic environment for the PostgreSQL vector store and MySQL app store.

Select the target with ``alembic -x database=postgres ...`` (default) or
``alembic -x database=mysql ...``. Database URLs always come from Settings;
the URL in alembic.ini is only a safe parser fallback.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.db.base import Base, MySQLBase
import app.models  # noqa: F401 -- registers every mapped model


config = context.config
target = context.get_x_argument(as_dictionary=True).get("database", "postgres")

if target not in {"postgres", "mysql"}:
    raise ValueError("-x database must be either 'postgres' or 'mysql'")

database_url = settings.DATABASE_URL if target == "postgres" else settings.MYSQL_DATABASE_URL
target_metadata = Base.metadata if target == "postgres" else MySQLBase.metadata
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

if config.config_file_name:
    fileConfig(config.config_file_name)


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations(database=target)


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations(database=target)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
