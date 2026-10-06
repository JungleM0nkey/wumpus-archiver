"""Background scrape job manager for the API.

This is the production adapter of :class:`~wumpus_archiver.api.scrape_control.ScrapeControl`.
It is the only module under ``api/`` that reaches Discord, and it does so lazily, inside
``_run_scrape``, so importing it (and the API package) never imports discord.py.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from wumpus_archiver.api.scrape_control import JobStatus, ScrapeJob, ScrapeProgress
from wumpus_archiver.storage.database import Database

if TYPE_CHECKING:
    from wumpus_archiver.bot.scraper import ArchiverBot

logger = logging.getLogger(__name__)

__all__ = ["JobStatus", "ScrapeJob", "ScrapeJobManager", "ScrapeProgress"]


class ScrapeJobManager:
    """Manages background scrape jobs.

    Only one scrape job can run at a time since we use a single bot connection.
    """

    configured: bool = True

    def __init__(self, database: Database, token: str) -> None:
        """Initialize the scrape job manager.

        Args:
            database: Database instance for storage
            token: The bot token every job runs under; must not be blank

        Raises:
            ValueError: If the token is empty or whitespace
        """
        if not token or not token.strip():
            raise ValueError("a scrape job manager needs a non-empty bot token")
        self.database = database
        self._token = token
        self._current_job: ScrapeJob | None = None
        self._task: asyncio.Task[None] | None = None
        self._bot: ArchiverBot | None = None
        self._cancel_requested = False
        self._history: list[ScrapeJob] = []

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

    def start_scrape(self, guild_id: int) -> ScrapeJob:
        """Start a new scrape job.

        Args:
            guild_id: Discord guild ID to scrape

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
            status=JobStatus.PENDING,
            started_at=datetime.now(UTC),
        )
        self._current_job = job
        self._cancel_requested = False

        # Launch the background task
        self._task = asyncio.create_task(self._run_scrape(job))
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

    async def _run_scrape(self, job: ScrapeJob) -> None:
        """Execute the scrape job in the background.

        Args:
            job: The job to execute
        """
        try:
            # Phase 1: Connect to Discord
            job.status = JobStatus.CONNECTING
            logger.info("Scrape job %s: connecting to Discord...", job.id)

            from wumpus_archiver.bot.scraper import ArchiverBot

            bot = ArchiverBot(self._token, self.database)
            self._bot = bot

            await bot.start()

            if self._cancel_requested:
                await bot.close()
                self._bot = None
                return

            # Phase 2: Run the scrape
            job.status = JobStatus.SCRAPING
            logger.info("Scrape job %s: scraping guild %d...", job.id, job.guild_id)

            def progress_callback(channel_name: str, message_count: int) -> None:
                """Update job progress from scraper callback."""
                job.progress.current_channel = channel_name
                job.progress.messages_scraped = message_count

            stats = await bot.scrape_guild(job.guild_id, progress_callback)

            # Phase 3: Record results
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
