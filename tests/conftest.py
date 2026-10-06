"""Shared test fixtures.

The HTTP fixtures build the app through the real factory. A test module changes
one collaborator by shadowing the matching value fixture (``attachments_dir``,
``portal_build`` or ``scrape``); the shared ``client`` is never overridden. The
default is what ``serve`` builds without a bot token: API only, read-only scrape
control, attachment URLs on the CDN.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.api.app import create_app
from wumpus_archiver.api.scrape_control import ScrapeControl
from wumpus_archiver.storage.database import Database


@pytest.fixture
async def database(tmp_path) -> AsyncGenerator[Database, None]:
    """A connected, empty archive on a file in ``tmp_path``. This fixture owns the connection."""
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


@pytest.fixture
def attachments_dir() -> Path | None:
    """Local attachments directory handed to the factory; shadow it to serve one."""
    return None


@pytest.fixture
def portal_build() -> Path | None:
    """Portal build handed to the factory; shadow it to serve a portal."""
    return None


@pytest.fixture
def scrape() -> ScrapeControl | None:
    """Scrape control handed to the factory; ``None`` is read-only, like serve without a token."""
    return None


@pytest.fixture
def app(
    database: Database,
    attachments_dir: Path | None,
    portal_build: Path | None,
    scrape: ScrapeControl | None,
) -> FastAPI:
    """The app under test, built by the real factory over the connected test database."""
    return create_app(
        database,
        attachments_dir=attachments_dir,
        portal_build=portal_build,
        scrape=scrape,
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """In-process HTTP client.

    ``ASGITransport`` never runs the lifespan, which is right: the ``database``
    fixture already connected the archive and keeps owning it.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
