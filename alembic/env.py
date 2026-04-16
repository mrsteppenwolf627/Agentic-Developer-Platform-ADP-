"""Alembic environment configuration.

Uses synchronous psycopg2 engine for migrations.
App uses asyncpg at runtime; they share the same DB with different drivers.
DATABASE_URL is loaded from the environment or .env file.
"""
import os
import sys
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

# Make app importable from alembic context
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.schemas import Base  # noqa: E402

config = context.config

load_dotenv()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Override sqlalchemy.url with env var if set, normalizing asyncpg -> psycopg2
_db_url = os.getenv("DATABASE_URL", "")
if _db_url.startswith("postgresql+asyncpg://"):
    _db_url = _db_url.replace("postgresql+asyncpg://", "postgresql://", 1)
if _db_url:
    _db_url_escaped = _db_url.replace("%", "%%")
    config.set_main_option("sqlalchemy.url", _db_url_escaped)


def run_migrations_offline() -> None:
    """Run migrations in offline mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
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
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
