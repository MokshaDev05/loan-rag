from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


# pgvector ≥ 0.3: the Vector type from pgvector.sqlalchemy handles encode/decode
# via SQLAlchemy's type system — no asyncpg-level register_vector needed here.
engine = create_async_engine(
    settings.DATABASE_URL,          # must begin with postgresql+asyncpg://
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=settings.DEBUG,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # async SQLAlchemy cannot lazy-load after commit; keep attrs accessible
    autoflush=False,          # flush explicitly so callers control when SQL is emitted
    autocommit=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that provides a transactional database session.

    Commits on clean exit.  Rolls back and re-raises on any exception so the
    caller's exception handler (or FastAPI's 500 handler) sees the original
    error, not a partially-committed state.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
