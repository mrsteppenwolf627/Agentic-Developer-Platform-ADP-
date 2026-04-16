"""Async SQLAlchemy engine and session factory.

Uses asyncpg driver for runtime (FastAPI).
Alembic migrations use synchronous psycopg2 — see alembic/env.py.

Environment variables:
  DATABASE_URL — must use postgresql+asyncpg:// scheme for runtime.
                 Supabase: postgresql+asyncpg://postgres:<password>@db.<project>.supabase.co:5432/postgres
"""
import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models import Base  # noqa: F401 — imported so metadata is populated

_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/adp",
)

# Ensure asyncpg driver for runtime
if _DATABASE_URL.startswith("postgresql://"):
    _DATABASE_URL = _DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    _DATABASE_URL,
    echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
