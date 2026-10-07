"""Shared test fixtures.

The HTTP fixtures build the app through the real factory. A test module changes
one collaborator by shadowing the matching value fixture (``attachments_dir``,
``portal_build`` or ``scrape``); the shared ``client`` is never overridden. The
default is what ``serve`` builds without a bot token: API only, read-only scrape
control, attachment URLs on the CDN.
"""

import shutil
from collections.abc import AsyncGenerator, AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.api.app import create_app
from wumpus_archiver.api.scrape_control import ScrapeControl
from wumpus_archiver.models.base import Base
from wumpus_archiver.storage.database import Database


@pytest.fixture(scope="session")
def empty_archive(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An archive file holding the schema and nothing else, built once per test run."""
    path = tmp_path_factory.mktemp("empty-archive") / "archive.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    engine.dispose()
    return path


def _without_fsync(dbapi_connection: Any, _record: Any) -> None:
    """Tests need no crash durability, so their SQLite connections skip the disk flushes."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA synchronous = OFF")
    cursor.execute("PRAGMA journal_mode = MEMORY")
    cursor.close()


@pytest.fixture
async def database(tmp_path: Path, empty_archive: Path) -> AsyncGenerator[Database, None]:
    """A connected, empty archive on a file in ``tmp_path``. This fixture owns the connection.

    The file starts as a copy of ``empty_archive`` rather than running the DDL again, and
    its connections skip fsync. ``Database.create_tables`` keeps its own tests.
    """
    db_path = tmp_path / "test.db"
    shutil.copyfile(empty_archive, db_path)
    db = Database(f"sqlite+aiosqlite:///{db_path}")
    await db.connect()
    event.listen(db.engine.sync_engine, "connect", _without_fsync)
    yield db
    await db.disconnect()


@pytest.fixture
def statements(database: Database) -> Iterator[list[str]]:
    """The SQL statements executed on ``database`` while the test runs."""
    seen: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        seen.append(statement)

    engine = database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    yield seen
    event.remove(engine, "before_cursor_execute", record)


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
