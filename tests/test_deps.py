"""Tests for how route handlers receive the app's collaborators."""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from wumpus_archiver.api.deps import (
    AttachmentsDir,
    Db,
    NotWiredError,
    Scrape,
    Wiring,
    bind,
    wiring_of,
)
from wumpus_archiver.api.scrape_control import ReadOnlyScrape
from wumpus_archiver.storage.database import Database

router = APIRouter()


@router.get("/db")
async def read_db(db: Db) -> dict[str, str]:
    return {"url": db.database_url}


@router.get("/attachments")
async def read_attachments(attachments_dir: AttachmentsDir) -> dict[str, str | None]:
    return {"dir": str(attachments_dir) if attachments_dir else None}


@router.get("/scrape")
async def read_scrape(scrape: Scrape) -> dict[str, bool]:
    return {"configured": scrape.configured}


@pytest.fixture
def wiring(tmp_path: Path) -> Wiring:
    return Wiring(
        database=Database("sqlite+aiosqlite:///:memory:"),
        attachments_dir=tmp_path,
        portal_build=None,
        scrape=ReadOnlyScrape(),
    )


@pytest.fixture
def wired_app(wiring: Wiring) -> FastAPI:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    bind(app, wiring)
    return app


@pytest.fixture
async def deps_client(wired_app: FastAPI) -> AsyncIterator[AsyncClient]:
    """A client over the hand-wired toy app, not the factory-built shared ``client``."""
    async with AsyncClient(transport=ASGITransport(app=wired_app), base_url="http://t") as http:
        yield http


class TestWiring:
    def test_wiring_of_returns_what_was_bound(self, wired_app: FastAPI, wiring: Wiring) -> None:
        assert wiring_of(wired_app) is wiring

    def test_binding_twice_is_an_error(self, wired_app: FastAPI, wiring: Wiring) -> None:
        with pytest.raises(RuntimeError, match="already wired"):
            bind(wired_app, wiring)

    def test_foreign_app_is_not_wired(self) -> None:
        with pytest.raises(NotWiredError, match="create_app"):
            wiring_of(FastAPI())

    def test_wiring_is_immutable(self, wiring: Wiring) -> None:
        with pytest.raises(AttributeError):
            wiring.attachments_dir = None  # type: ignore[misc]


class TestDependencies:
    async def test_handlers_receive_each_collaborator(
        self, deps_client: AsyncClient, wiring: Wiring
    ) -> None:
        assert (await deps_client.get("/api/db")).json() == {"url": "sqlite+aiosqlite:///:memory:"}
        assert (await deps_client.get("/api/attachments")).json() == {
            "dir": str(wiring.attachments_dir)
        }
        assert (await deps_client.get("/api/scrape")).json() == {"configured": False}

    async def test_dependencies_add_no_parameters_to_openapi(self, wired_app: FastAPI) -> None:
        paths = wired_app.openapi()["paths"]
        for path in ("/api/db", "/api/attachments", "/api/scrape"):
            assert "parameters" not in paths[path]["get"]

    async def test_foreign_app_fails_every_request_with_one_error(self) -> None:
        app = FastAPI()
        app.include_router(router, prefix="/api")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            for path in ("/api/db", "/api/attachments", "/api/scrape"):
                with pytest.raises(NotWiredError):
                    await http.get(path)
