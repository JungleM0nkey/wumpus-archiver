"""Tests for the scrape control port and its read-only adapter."""

import subprocess
import sys

import pytest

from tests.fakes import FakeScrapeControl
from wumpus_archiver.api.scrape_control import ReadOnlyScrape, ScrapeControl
from wumpus_archiver.api.scrape_manager import ScrapeJobManager
from wumpus_archiver.storage.database import Database


class TestReadOnlyScrape:
    """The adapter used whenever no bot token is configured."""

    def test_satisfies_the_port(self) -> None:
        assert isinstance(ReadOnlyScrape(), ScrapeControl)

    def test_reports_nothing(self) -> None:
        scrape = ReadOnlyScrape()
        assert scrape.configured is False
        assert scrape.is_busy is False
        assert scrape.current_job is None
        assert scrape.history == []

    def test_cannot_start_or_cancel(self) -> None:
        scrape = ReadOnlyScrape()
        with pytest.raises(RuntimeError, match="read-only"):
            scrape.start_scrape(123)
        assert scrape.cancel() is False


class TestScrapeJobManager:
    """The production adapter owns its token and satisfies the port."""

    def test_satisfies_the_port(self) -> None:
        manager = ScrapeJobManager(Database("sqlite+aiosqlite:///:memory:"), "token")
        assert isinstance(manager, ScrapeControl)
        assert manager.configured is True
        assert manager.is_busy is False
        assert manager.current_job is None
        assert manager.history == []
        assert manager.cancel() is False

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_rejects_a_blank_token(self, blank: str) -> None:
        with pytest.raises(ValueError, match="non-empty bot token"):
            ScrapeJobManager(Database("sqlite+aiosqlite:///:memory:"), blank)


class TestFakeScrapeControl:
    """The test adapter satisfies the port and can be preset."""

    def test_satisfies_the_port(self) -> None:
        assert isinstance(FakeScrapeControl(), ScrapeControl)

    def test_start_busy_finish_history(self) -> None:
        fake = FakeScrapeControl()
        job = fake.start_scrape(42)
        assert fake.is_busy and fake.current_job is job
        with pytest.raises(RuntimeError):
            fake.start_scrape(43)
        finished = fake.finish(messages_scraped=5)
        assert finished.result == {"messages_scraped": 5}
        assert fake.is_busy is False
        assert fake.history == [finished]


def test_scrape_manager_module_does_not_import_discord() -> None:
    """Importing the manager (and the API package with it) must not load discord.py.

    Runs in a subprocess because the test process already imported discord through the CLI.
    """
    code = (
        "import sys\n"
        "import wumpus_archiver.api.scrape_manager\n"
        "import wumpus_archiver.api.scrape_control\n"
        "loaded = sorted(m for m in sys.modules if m == 'discord' or m.startswith('discord.')"
        " or m.startswith('wumpus_archiver.bot'))\n"
        "print(loaded)\n"
        "sys.exit(1 if loaded else 0)\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
