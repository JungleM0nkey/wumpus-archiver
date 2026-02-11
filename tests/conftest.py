"""Shared test fixtures."""

import asyncio
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.storage.database import Database


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def database(tmp_path) -> AsyncGenerator[Database, None]:
    """Create an in-memory test database."""
    db_path = tmp_path / "test.db"
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.connect()
    await db.create_tables()
    yield db
    await db.disconnect()


@pytest.fixture
async def session(database: Database) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for testing."""
    async with database.session() as session:
        yield session
