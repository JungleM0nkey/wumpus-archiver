"""Tests for the scrape control port and its read-only adapter."""

import asyncio
import subprocess
import sys
from collections.abc import AsyncIterator, Callable
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.fakes import FakeScrapeControl
from wumpus_archiver.api.scrape_control import (
    JobStatus,
    ReadOnlyScrape,
    ScrapeControl,
    ScrapeProgress,
)
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


class TestScrapeProgress:
    """Per-channel progress follows the scraper's reports, one channel at a time."""

    def test_a_report_for_the_next_channel_marks_the_last_one_done(self) -> None:
        progress = ScrapeProgress()
        progress.record_channel("general", 100)
        progress.record_channel("general", 140)
        progress.record_channel("art", 0)
        progress.record_channel("memes", 200)

        assert [(c.name, c.messages, c.done) for c in progress.channels] == [
            ("general", 140, True),
            ("art", 0, True),
            ("memes", 200, False),
        ]
        assert progress.current_channel == "memes"
        assert progress.channels_done == 2
        assert progress.messages_scraped == 340

    def test_finishing_marks_every_channel_done(self) -> None:
        progress = ScrapeProgress()
        progress.record_channel("general", 3)
        progress.record_channel("art", 4)
        progress.finish_channels()
        assert all(c.done for c in progress.channels)
        assert progress.channels_done == 2

    def test_jobs_do_not_share_progress(self) -> None:
        fake = FakeScrapeControl()
        fake.start_scrape(1)
        fake.report("general", 5)
        first = fake.finish()
        fake.start_scrape(2)
        assert fake.current_job is not None
        assert fake.current_job.progress.channels == []
        assert [c.name for c in first.progress.channels] == ["general"]


class FakeBot:
    """Stands in for ArchiverBot inside the manager's job: reports channels, then waits."""

    instances: list["FakeBot"] = []

    def __init__(self, token: str, database: Any) -> None:
        self.release = asyncio.Event()
        self.closed = False
        self.fail_on_close = False
        self.progress: Callable[[str, int], None] | None = None
        FakeBot.instances.append(self)

    async def start(self) -> None:
        return None

    async def scrape_guild(
        self, guild_id: int, progress: Callable[[str, int], None]
    ) -> dict[str, object]:
        self.progress = progress
        progress("general", 100)
        progress("general", 120)
        progress("art", 7)
        await self.release.wait()
        if self.closed:
            raise RuntimeError("Session is closed")
        return {
            "channels_scraped": 2,
            "messages_scraped": 127,
            "attachments_found": 3,
            "errors": [],
        }

    async def close(self) -> None:
        self.closed = True
        self.release.set()


@pytest.fixture
def fake_bot(monkeypatch: pytest.MonkeyPatch) -> type[FakeBot]:
    """The manager's jobs run on FakeBot instead of connecting to Discord."""
    import wumpus_archiver.bot.scraper as scraper

    FakeBot.instances = []
    monkeypatch.setattr(scraper, "ArchiverBot", FakeBot)
    return FakeBot


async def settle() -> None:
    """Let the job's task run until it waits again."""
    for _ in range(5):
        await asyncio.sleep(0)


class TestScrapeJobManagerProgress:
    """The manager reports each channel as the scraper works through them."""

    async def test_reports_each_channel_and_finishes_them(self, fake_bot: type[FakeBot]) -> None:
        manager = ScrapeJobManager(Database("sqlite+aiosqlite:///:memory:"), "token")
        job = manager.start_scrape(42)
        await settle()

        assert manager.is_busy
        progress = job.progress
        assert [(c.name, c.messages, c.done) for c in progress.channels] == [
            ("general", 120, True),
            ("art", 7, False),
        ]
        assert (progress.current_channel, progress.channels_done, progress.messages_scraped) == (
            "art",
            1,
            127,
        )

        fake_bot.instances[0].release.set()
        await settle()
        assert job.status == JobStatus.COMPLETED
        assert all(c.done for c in job.progress.channels)
        assert (job.progress.channels_done, job.progress.attachments_found) == (2, 3)
        assert [j.id for j in manager.history] == [job.id]

    async def test_a_cancelled_job_is_in_the_history_at_once_and_stays_cancelled(
        self, fake_bot: type[FakeBot]
    ) -> None:
        manager = ScrapeJobManager(Database("sqlite+aiosqlite:///:memory:"), "token")
        job = manager.start_scrape(42)
        await settle()

        assert manager.cancel() is True
        assert not manager.is_busy
        assert [(j.id, j.status) for j in manager.history] == [(job.id, JobStatus.CANCELLED)]

        # Closing the connection makes the scrape raise; the job stays cancelled, once.
        await settle()
        assert fake_bot.instances[0].closed
        assert job.status == JobStatus.CANCELLED
        assert job.error_message is None
        assert [(j.id, j.status) for j in manager.history] == [(job.id, JobStatus.CANCELLED)]


async def test_the_scraper_reports_every_channel_once_it_is_written(session: AsyncSession) -> None:
    """A channel too short for a batch report still reports its final count when done."""
    from wumpus_archiver.bot.scraper import ArchiverBot

    async def no_history(**_kwargs: Any) -> AsyncIterator[Any]:
        return
        yield

    channel = SimpleNamespace(
        id=900_001,
        guild=SimpleNamespace(id=900_000),
        name="quiet",
        type=SimpleNamespace(value=0),
        topic=None,
        position=0,
        parent_id=None,
        category_id=None,
        history=no_history,
    )
    reports: list[tuple[str, int]] = []
    bot = ArchiverBot.__new__(ArchiverBot)
    await bot._scrape_channel(session, channel, lambda name, n: reports.append((name, n)))  # type: ignore[arg-type]
    assert reports == [("quiet", 0)]


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
