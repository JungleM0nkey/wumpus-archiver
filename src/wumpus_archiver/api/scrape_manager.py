"""Background scrape job manager for the API."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from wumpus_archiver.bot.scraper import ArchiverBot
from wumpus_archiver.storage.database import Database, DatabaseRegistry

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    """Scrape job status."""

    PENDING = "pending"
    CONNECTING = "connecting"
    SCRAPING = "scraping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScrapeProgress(BaseModel):
    """Progress data for a running scrape job."""

    current_channel: str = ""
    channels_done: int = 0
    channels_total: int = 0
    messages_scraped: int = 0
    attachments_found: int = 0
    errors: list[str] = []


class ScrapeJob(BaseModel):
    """Represents a single scrape job."""

    id: str
    guild_id: int
    channel_ids: list[int] | None = None  # None = full guild scrape
    status: JobStatus = JobStatus.PENDING
    progress: ScrapeProgress = ScrapeProgress()
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_message: str | None = None


class ScrapeJobManager:
    """Manages background scrape jobs.

    Only one scrape job can run at a time since we use a single bot connection.
    """

    def __init__(self, registry: DatabaseRegistry) -> None:
        """Initialize the scrape job manager.

        Args:
            registry: Database registry for accessing the active data source
        """
        self._registry = registry
        self._current_job: ScrapeJob | None = None
        self._task: asyncio.Task[None] | None = None
        self._bot: ArchiverBot | None = None
        self._cancel_requested = False
        self._history: list[ScrapeJob] = []

    @property
    def database(self) -> Database:
        """Get the currently active database."""
        return self._registry.get_active()

    async def fetch_live_channels(self, token: str, guild_id: int) -> list[dict] | None:
        """Fetch live channel list from Discord HTTP API.

        Uses discord.http.HTTPClient directly for a single REST call
        instead of connecting a full gateway bot.

        Returns list of channel dicts or None on failure.
        """
        try:
            import discord.http

            http = discord.http.HTTPClient(loop=asyncio.get_running_loop())
            try:
                await http.static_login(token)
                channels = await http.get_all_guild_channels(guild_id)
                return channels  # type: ignore[return-value]
            finally:
                await http.close()
        except Exception as e:
            logger.warning("Failed to fetch live channels for guild %d: %s", guild_id, e)
            return None

    @property
    def current_job(self) -> ScrapeJob | None:
        """Get the current running job, if any."""
        return self._current_job

    @property
    def history(self) -> list[ScrapeJob]:
        """Get completed job history (most recent first)."""
        return list(reversed(self._history))

    @property
    def is_busy(self) -> bool:
        """Check if a job is currently running."""
        return (
            self._current_job is not None
            and self._current_job.status in (JobStatus.PENDING, JobStatus.CONNECTING, JobStatus.SCRAPING)
        )

    def start_scrape(
        self,
        guild_id: int,
        token: str,
        channel_ids: list[int] | None = None,
    ) -> ScrapeJob:
        """Start a new scrape job.

        Args:
            guild_id: Discord guild ID to scrape
            token: Discord bot token
            channel_ids: Optional list of specific channel IDs to scrape.
                If None, scrapes all channels in the guild.

        Returns:
            The created ScrapeJob

        Raises:
            RuntimeError: If a job is already running
        """
        if self.is_busy:
            raise RuntimeError("A scrape job is already running")

        job = ScrapeJob(
            id=uuid.uuid4().hex[:12],
            guild_id=guild_id,
            channel_ids=channel_ids,
            status=JobStatus.PENDING,
            started_at=datetime.now(UTC),
        )
        self._current_job = job
        self._cancel_requested = False

        # Launch the background task
        self._task = asyncio.create_task(self._run_scrape(job, token))
        return job

    def cancel(self) -> bool:
        """Request cancellation of the current job.

        Returns:
            True if a cancellation was requested, False if no job to cancel
        """
        if not self.is_busy or self._current_job is None:
            return False

        self._cancel_requested = True
        self._current_job.status = JobStatus.CANCELLED
        self._current_job.completed_at = datetime.now(UTC)

        # Force-close the bot if running
        if self._bot is not None:
            asyncio.create_task(self._force_close_bot())

        return True

    async def _force_close_bot(self) -> None:
        """Force close the bot connection."""
        if self._bot is not None:
            try:
                await self._bot.close()
            except Exception:
                pass
            self._bot = None

    async def _run_scrape(self, job: ScrapeJob, token: str) -> None:
        """Execute the scrape job in the background.

        Args:
            job: The job to execute
            token: Discord bot token
        """
        try:
            # Phase 1: Connect to Discord
            job.status = JobStatus.CONNECTING
            logger.info("Scrape job %s: connecting to Discord...", job.id)

            bot = ArchiverBot(token, self.database)
            self._bot = bot

            await bot.start()

            if self._cancel_requested:
                await bot.close()
                self._bot = None
                return

            # Phase 2: Run the scrape
            job.status = JobStatus.SCRAPING
            if job.channel_ids:
                job.progress.channels_total = len(job.channel_ids)
                logger.info(
                    "Scrape job %s: scraping %d channels in guild %d...",
                    job.id,
                    len(job.channel_ids),
                    job.guild_id,
                )
            else:
                logger.info("Scrape job %s: scraping guild %d...", job.id, job.guild_id)

            # Track cumulative progress across channels
            cumulative_messages = 0
            cumulative_attachments = 0
            cumulative_channels = 0

            def progress_callback(channel_name: str, message_count: int) -> None:
                """Update job progress from scraper callback."""
                job.progress.current_channel = channel_name
                job.progress.messages_scraped = cumulative_messages + message_count

            def channel_done_callback(
                ch_messages: int, ch_attachments: int
            ) -> None:
                """Called when a channel finishes scraping."""
                nonlocal cumulative_messages, cumulative_attachments, cumulative_channels
                cumulative_messages += ch_messages
                cumulative_attachments += ch_attachments
                cumulative_channels += 1
                job.progress.channels_done = cumulative_channels
                job.progress.messages_scraped = cumulative_messages
                job.progress.attachments_found = cumulative_attachments

            if job.channel_ids:
                stats = await bot.scrape_channels(
                    job.guild_id,
                    job.channel_ids,
                    progress_callback,
                    channel_done_callback,
                )
            else:
                stats = await bot.scrape_guild(
                    job.guild_id, progress_callback, channel_done_callback
                )
                # For full guild scrape, update total from result
                if not job.progress.channels_total:
                    job.progress.channels_total = int(stats.get("channels_scraped", 0))

            # Phase 3: Record final results
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.now(UTC)
            job.result = stats
            job.progress.channels_done = int(stats.get("channels_scraped", 0))
            job.progress.messages_scraped = int(stats.get("messages_scraped", 0))
            job.progress.attachments_found = int(stats.get("attachments_found", 0))
            job.progress.errors = [str(e) for e in stats.get("errors", [])]

            logger.info(
                "Scrape job %s: completed — %d channels, %d messages",
                job.id,
                job.progress.channels_done,
                job.progress.messages_scraped,
            )

        except asyncio.CancelledError:
            job.status = JobStatus.CANCELLED
            job.completed_at = datetime.now(UTC)
            logger.info("Scrape job %s: cancelled", job.id)

        except Exception as e:
            job.status = JobStatus.FAILED
            job.completed_at = datetime.now(UTC)
            job.error_message = str(e)
            logger.error("Scrape job %s: failed — %s", job.id, e)

        finally:
            # Always clean up the bot
            if self._bot is not None:
                try:
                    await self._bot.close()
                except Exception:
                    pass
                self._bot = None

            # Archive to history
            if self._current_job is not None:
                self._history.append(self._current_job.model_copy())
                # Keep only last 50 jobs
                if len(self._history) > 50:
                    self._history = self._history[-50:]
