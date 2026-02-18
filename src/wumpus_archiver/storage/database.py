"""Database connection and session management."""

import asyncio
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


class DatabaseRegistry:
    """Manages multiple database sources with runtime switching."""

    def __init__(self) -> None:
        self.sources: dict[str, Database] = {}
        self.source_urls: dict[str, str] = {}
        self._active: str = "sqlite"
        self._lock: asyncio.Lock | None = None

    def register(self, name: str, database: Database, url: str) -> None:
        """Register a named database source."""
        self.sources[name] = database
        self.source_urls[name] = url
        if len(self.sources) == 1:
            self._active = name

    @property
    def active(self) -> str:
        """Get the name of the active source."""
        return self._active

    def get_active(self) -> Database:
        """Get the currently active database."""
        if self._active not in self.sources:
            raise RuntimeError(f"Active data source '{self._active}' not registered")
        return self.sources[self._active]

    def set_active(self, name: str) -> None:
        """Switch the active data source (sync, for initial setup)."""
        if name not in self.sources:
            raise KeyError(f"Unknown data source: '{name}'. Available: {list(self.sources.keys())}")
        self._active = name

    async def set_active_safe(self, name: str) -> None:
        """Switch the active data source (async, lock-protected for runtime use)."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            if name not in self.sources:
                raise KeyError(f"Unknown data source: '{name}'. Available: {list(self.sources.keys())}")
            self._active = name

    @property
    def available_sources(self) -> list[str]:
        """List registered source names."""
        return list(self.sources.keys())

    async def connect_all(self) -> None:
        """Connect and create tables for all registered sources."""
        for _name, db in self.sources.items():
            await db.connect()
            await db.create_tables()

    async def disconnect_all(self) -> None:
        """Disconnect all registered sources."""
        for db in self.sources.values():
            await db.disconnect()

