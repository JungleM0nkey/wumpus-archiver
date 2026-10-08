"""Test adapters for the project's ports."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from wumpus_archiver.api.scrape_control import JobStatus, ScrapeJob
from wumpus_archiver.storage.database import Database

if TYPE_CHECKING:
    from wumpus_archiver.bot.scraper import ArchiverBot

_ACTIVE = (JobStatus.PENDING, JobStatus.CONNECTING, JobStatus.SCRAPING)


class FakeScrapeControl:
    """Scrape control that records starts and never opens a gateway connection.

    Pre-settable so a test (or a screenshot harness) can present a busy job or a
    history without starting anything.
    """

    configured: bool = True

    def __init__(
        self,
        *,
        current_job: ScrapeJob | None = None,
        history: list[ScrapeJob] | None = None,
    ) -> None:
        self.current_job = current_job
        self._history: list[ScrapeJob] = list(history or [])
        self.started: list[int] = []

    @property
    def is_busy(self) -> bool:
        return self.current_job is not None and self.current_job.status in _ACTIVE

    @property
    def history(self) -> list[ScrapeJob]:
        return list(reversed(self._history))

    def start_scrape(self, guild_id: int) -> ScrapeJob:
        if self.is_busy:
            raise RuntimeError("A scrape job is already running")
        self.started.append(guild_id)
        self.current_job = ScrapeJob(
            id=f"job{len(self.started)}",
            guild_id=guild_id,
            status=JobStatus.SCRAPING,
            started_at=datetime.now(UTC),
        )
        return self.current_job

    def cancel(self) -> bool:
        if not self.is_busy or self.current_job is None:
            return False
        self.current_job.status = JobStatus.CANCELLED
        self.current_job.completed_at = datetime.now(UTC)
        self._history.append(self.current_job)
        return True

    def report(self, channel: str, messages: int) -> None:
        """Report progress of the current job as the scraper does: ``messages`` written in ``channel``."""
        if self.current_job is None:
            raise RuntimeError("no job to report on")
        self.current_job.progress.record_channel(channel, messages)

    def finish(self, **result: Any) -> ScrapeJob:
        """Complete the current job with ``result`` and move it to the history."""
        if self.current_job is None:
            raise RuntimeError("no job to finish")
        job = self.current_job
        job.status = JobStatus.COMPLETED
        job.completed_at = datetime.now(UTC)
        job.result = result
        job.progress.finish_channels()
        self._history.append(job)
        self.current_job = None
        return job


class FakeDiscordChannel:
    """A Discord text channel as ``ArchiverBot`` reads it, over a list of message ids.

    ``history`` yields a message per id, newest first, as discord.py does with
    ``oldest_first=False``. ``post`` adds messages between scrapes.
    """

    def __init__(self, guild: "FakeDiscordGuild", channel_id: int, name: str) -> None:
        self.guild = guild
        self.id = channel_id
        self.name = name
        self.type = SimpleNamespace(value=0)
        self.topic: str | None = None
        self.position = 0
        self.parent_id: int | None = None
        self.category_id: int | None = None
        self.message_ids: list[int] = []

    def post(self, *message_ids: int) -> None:
        self.message_ids.extend(message_ids)

    async def history(
        self, *, limit: int | None = None, oldest_first: bool = False
    ) -> AsyncIterator[Any]:
        ids = sorted(self.message_ids, reverse=not oldest_first)[:limit]
        for message_id in ids:
            yield _fake_discord_message(self, message_id)

    async def archived_threads(self, *, limit: int | None = None) -> AsyncIterator[Any]:
        return
        yield


class FakeDiscordGuild:
    """A Discord guild of text channels only, as ``ArchiverBot.scrape_guild`` reads it."""

    def __init__(self, guild_id: int, name: str = "Fake guild") -> None:
        self.id = guild_id
        self.name = name
        self.icon = None
        self.owner_id: int | None = None
        self.member_count = 1
        self.text_channels: list[FakeDiscordChannel] = []
        self.voice_channels: list[Any] = []
        self.stage_channels: list[Any] = []
        self.forum_channels: list[Any] = []
        self.threads: list[Any] = []

    def add_channel(self, channel_id: int, name: str, *message_ids: int) -> FakeDiscordChannel:
        channel = FakeDiscordChannel(self, channel_id, name)
        channel.post(*message_ids)
        self.text_channels.append(channel)
        return channel


FAKE_DISCORD_AUTHOR = SimpleNamespace(
    id=7_000, name="wumpus", discriminator="0", global_name="Wumpus", avatar=None, bot=False
)


def _fake_discord_message(channel: FakeDiscordChannel, message_id: int) -> Any:
    return SimpleNamespace(
        id=message_id,
        channel=channel,
        author=FAKE_DISCORD_AUTHOR,
        content=f"message {message_id}",
        clean_content=f"message {message_id}",
        created_at=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=message_id % 100_000),
        edited_at=None,
        pinned=False,
        tts=False,
        mention_everyone=False,
        embeds=[],
        reference=None,
        attachments=[],
        reactions=[],
    )


def fake_archiver_bot(database: Database, *guilds: FakeDiscordGuild) -> "ArchiverBot":
    """A real ``ArchiverBot`` over ``database`` whose gateway client knows only ``guilds``.

    Nothing connects: the bot is never started, and ``get_guild`` answers from the fakes.
    """
    from wumpus_archiver.bot.scraper import ArchiverBot

    by_id = {guild.id: guild for guild in guilds}
    bot = ArchiverBot.__new__(ArchiverBot)
    bot.database = database
    bot.client = SimpleNamespace(get_guild=by_id.get)  # type: ignore[assignment]
    return bot
