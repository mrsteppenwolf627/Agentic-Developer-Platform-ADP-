"""Alembic environment configuration."""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOTENV_PATH = PROJECT_ROOT / ".env"

from app.models.schemas import Base

config = context.config

try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=str(DOTENV_PATH), override=True)
    print(f"[Alembic] Loaded .env from: {DOTENV_PATH}")
except Exception as e:
    print(f"[Alembic] Warning: Could not load .env: {e}")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_db_url = os.getenv("DATABASE_URL")

print(f"[Alembic] DATABASE_URL exists: {bool(_db_url)}")
if _db_url:
    print(f"[Alembic] DATABASE_URL (first 60 chars): {_db_url[:60]}...")

if not _db_url:
    raise ValueError(
        f"DATABASE_URL not set. "
        f"Check .env file at: {DOTENV_PATH}\n"
        f".env exists: {DOTENV_PATH.exists()}\n"
        f"Env vars available: {list(os.environ.keys())}"
    )

if _db_url.startswith("postgresql+asyncpg://"):
    _db_url = _db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

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
