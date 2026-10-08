"""Test adapters for the project's ports."""

from datetime import UTC, datetime
from typing import Any

from wumpus_archiver.api.scrape_control import JobStatus, ScrapeJob

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
