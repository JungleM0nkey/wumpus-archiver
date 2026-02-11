"""Database connection and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from wumpus_archiver.models.base import Base


class Database:
    """Database manager for async SQLAlchemy operations."""

    def __init__(self, database_url: str) -> None:
        """Initialize database with connection URL.

        Args:
            database_url: SQLAlchemy async database URL
        """
        self.database_url = database_url
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        """Create database engine and session maker."""
        self._engine = create_async_engine(
            self.database_url,
            echo=False,
            future=True,
        )
        self._session_maker = async_sessionmaker(
            self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def disconnect(self) -> None:
        """Close database connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_maker = None

    async def create_tables(self) -> None:
        """Create all database tables."""
        if not self._engine:
            raise RuntimeError("Database not connected. Call connect() first.")

        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get a database session as async context manager.

        Yields:
            AsyncSession: Database session
        """
        if not self._session_maker:
            raise RuntimeError("Database not connected. Call connect() first.")

        session = self._session_maker()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @property
    def engine(self) -> AsyncEngine:
        """Get the database engine."""
        if not self._engine:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._engine
