"""Tests for the app factory's interface: what it takes, what it never reads, what it builds."""

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tests.fakes import FakeScrapeControl
from wumpus_archiver.api.app import create_app
from wumpus_archiver.api.deps import wiring_of
from wumpus_archiver.api.scrape_control import JobStatus, ReadOnlyScrape, ScrapeControl
from wumpus_archiver.storage.database import Database


def _run_in_subprocess(code: str) -> subprocess.CompletedProcess[str]:
    """Run ``code`` in a fresh interpreter, where nothing has imported discord yet."""
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


FORBIDDEN_MODULES = (
    "discord",
    "wumpus_archiver.bot",
    "wumpus_archiver.config",
    "wumpus_archiver.api.scrape_manager",
    "wumpus_archiver.compose",
    "wumpus_archiver.utils.process_manager",
)

LOADED_FORBIDDEN = (
    "import sys\n"
    f"forbidden = {FORBIDDEN_MODULES!r}\n"
    "loaded = sorted(m for m in sys.modules"
    " if any(m == f or m.startswith(f + '.') for f in forbidden))\n"
    "print(loaded)\n"
    "sys.exit(1 if loaded else 0)\n"
)


class TestReadsNothingFromTheEnvironment:
    async def test_planted_token_sources_are_ignored(
        self, database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A .env in the working directory, an env var, and Settings itself are all unused."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("DISCORD_BOT_TOKEN=leaked-from-dotenv\n")
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "leaked-from-env")

        def settings_must_not_be_instantiated(*args: object, **kwargs: object) -> None:
            raise AssertionError("create_app instantiated Settings")

        monkeypatch.setattr("wumpus_archiver.config.Settings", settings_must_not_be_instantiated)

        app = create_app(database)

        assert isinstance(wiring_of(app).scrape, ReadOnlyScrape)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            status = await http.get("/api/scrape/status")
            assert status.json()["has_token"] is False
            assert (await http.post("/api/scrape/start", json={"guild_id": 1})).status_code == 400

    async def test_a_discoverable_portal_build_is_not_picked_up(
        self, database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A portal build where the old package-relative or cwd lookups would find it is ignored."""
        import wumpus_archiver.api.app as app_module

        for root in (tmp_path / "cwd", tmp_path / "pkg"):
            build = root / "portal" / "build"
            build.mkdir(parents=True)
            (root / "portal" / "package.json").write_text("{}")
            (build / "index.html").write_text("<!doctype html><title>should not be served</title>")
        monkeypatch.chdir(tmp_path / "cwd")
        monkeypatch.setattr(
            app_module,
            "__file__",
            str(tmp_path / "pkg" / "src" / "wumpus_archiver" / "api" / "app.py"),
        )

        app = create_app(database)

        assert wiring_of(app).portal_build is None
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            assert (await http.get("/")).status_code == 404

    def test_read_only_app_imports_no_discord_no_config(self) -> None:
        """Building a read-only app loads neither discord.py nor the settings machinery."""
        code = (
            "from wumpus_archiver.api import create_app\n"
            "from wumpus_archiver.storage.database import Database\n"
            "app = create_app(Database('sqlite+aiosqlite:///:memory:'))\n" + LOADED_FORBIDDEN
        )
        result = _run_in_subprocess(code)
        assert result.returncode == 0, result.stdout + result.stderr

    def test_configured_app_imports_no_discord_until_a_job_starts(self) -> None:
        """A real scrape job manager with a token still loads discord only when a job runs."""
        code = (
            "from wumpus_archiver.api import create_app\n"
            "from wumpus_archiver.api.scrape_manager import ScrapeJobManager\n"
            "from wumpus_archiver.storage.database import Database\n"
            "db = Database('sqlite+aiosqlite:///:memory:')\n"
            "app = create_app(db, scrape=ScrapeJobManager(db, 'token'))\n"
            "import sys\n"
            "assert not any(m == 'discord' or m.startswith('discord.') for m in sys.modules)\n"
        )
        result = _run_in_subprocess(code)
        assert result.returncode == 0, result.stdout + result.stderr


class TestReadOnlyScrapeControl:
    """The default client is what serve builds without a token."""

    async def test_status_start_cancel_history(self, client: AsyncClient) -> None:
        status = await client.get("/api/scrape/status")
        assert status.status_code == 200
        assert status.json() == {"busy": False, "current_job": None, "has_token": False}

        start = await client.post("/api/scrape/start", json={"guild_id": 1})
        assert start.status_code == 400
        assert "read-only" in start.json()["error"]

        assert (await client.post("/api/scrape/cancel")).status_code == 404
        assert (await client.get("/api/scrape/history")).json() == {"jobs": []}


class TestConfiguredScrapeControl:
    """With an adapter that can start jobs, the routes drive it and never touch Discord."""

    @pytest.fixture
    def fake(self) -> FakeScrapeControl:
        return FakeScrapeControl()

    @pytest.fixture
    def scrape(self, fake: FakeScrapeControl) -> ScrapeControl:
        return fake

    async def test_full_job_round_trip(self, client: AsyncClient, fake: FakeScrapeControl) -> None:
        assert (await client.get("/api/scrape/status")).json()["has_token"] is True

        start = await client.post("/api/scrape/start", json={"guild_id": 7})
        assert start.status_code == 202
        assert start.json()["job"]["guild_id"] == 7
        assert fake.started == [7]

        assert (await client.post("/api/scrape/start", json={"guild_id": 8})).status_code == 409

        status = (await client.get("/api/scrape/status")).json()
        assert status["busy"] is True
        assert status["current_job"]["status"] == JobStatus.SCRAPING.value

        fake.finish(messages_scraped=12)
        history = (await client.get("/api/scrape/history")).json()["jobs"]
        assert [j["status"] for j in history] == [JobStatus.COMPLETED.value]
        assert history[0]["result"] == {"messages_scraped": 12}

    async def test_cancel_marks_the_job_cancelled(self, client: AsyncClient) -> None:
        await client.post("/api/scrape/start", json={"guild_id": 7})
        assert (await client.post("/api/scrape/cancel")).status_code == 200
        status = (await client.get("/api/scrape/status")).json()
        assert status["busy"] is False
        assert status["current_job"]["status"] == JobStatus.CANCELLED.value


class TestConnectionOwnership:
    """ADR 0001: connect only what was not connected; disconnect only what we connected."""

    async def test_fresh_database_is_connected_for_the_lifespan_only(self, tmp_path: Path) -> None:
        db = Database(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
        app = create_app(db)
        assert db.connected is False, "construction never touches the database"

        async with app.router.lifespan_context(app):
            assert db.connected is True
            await db.create_tables()
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
                assert (await http.get("/api/guilds")).json() == []

        assert db.connected is False

    async def test_a_connected_database_is_left_to_its_owner(self, database: Database) -> None:
        app = create_app(database)
        engine_before = database.engine

        async with app.router.lifespan_context(app):
            assert database.engine is engine_before, "no reconnect"

        assert database.connected is True, "the fixture still owns the connection"


class TestDirectoriesArePromises:
    def test_missing_attachments_dir_is_loud(self, database: Database, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="does not exist"):
            create_app(database, attachments_dir=tmp_path / "missing")

    def test_portal_build_without_index_is_loud(self, database: Database, tmp_path: Path) -> None:
        (tmp_path / "build").mkdir()
        with pytest.raises(FileNotFoundError, match="index.html"):
            create_app(database, portal_build=tmp_path / "build")

    async def test_attachments_dir_is_served(self, database: Database, tmp_path: Path) -> None:
        (tmp_path / "123").mkdir()
        (tmp_path / "123" / "photo.txt").write_text("photo")
        app = create_app(database, attachments_dir=tmp_path)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            assert (await http.get("/attachments/123/photo.txt")).text == "photo"
        assert wiring_of(app).attachments_dir == tmp_path.resolve()


class TestPortal:
    async def test_without_a_portal_the_root_is_404_and_the_api_is_served(
        self, client: AsyncClient
    ) -> None:
        assert (await client.get("/")).status_code == 404
        assert (await client.get("/api/guilds")).status_code == 200

    async def test_api_router_precedes_the_spa_fallback(
        self, database: Database, tmp_path: Path
    ) -> None:
        build = tmp_path / "build"
        build.mkdir()
        (build / "index.html").write_text("<!doctype html><title>portal</title>")
        app = create_app(database, portal_build=build)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as http:
            assert (await http.get("/api/guilds")).json() == []
            fallback = await http.get("/some/client/route")
            assert fallback.status_code == 200
            assert "portal" in fallback.text
        assert wiring_of(app).portal_build == build.resolve()


class TestFixtureShape:
    """The shared fixtures are the one way tests vary a collaborator."""

    @pytest.fixture
    def scrape(self) -> ScrapeControl:
        return FakeScrapeControl()

    async def test_a_module_can_shadow_one_knob(self, app: FastAPI) -> None:
        assert isinstance(wiring_of(app).scrape, FakeScrapeControl)
        assert wiring_of(app).attachments_dir is None
        assert wiring_of(app).portal_build is None


@pytest.mark.parametrize(
    "build",
    [
        lambda db: create_app(db),
        lambda db: create_app(db, scrape=None),
        lambda db: create_app(db, scrape=ReadOnlyScrape()),
    ],
    ids=["default", "explicit-none", "explicit-read-only"],
)
def test_read_only_is_one_object(database: Database, build: Callable[[Database], FastAPI]) -> None:
    assert isinstance(wiring_of(build(database)).scrape, ReadOnlyScrape)
