"""Tests for the scrape control port and its read-only adapter."""

import subprocess
import sys

import pytest

from wumpus_archiver.api.scrape_control import ReadOnlyScrape, ScrapeControl


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
