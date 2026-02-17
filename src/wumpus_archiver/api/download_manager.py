"""Background download job manager for the API."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from wumpus_archiver.storage.database import Database
from wumpus_archiver.utils.downloader import ImageDownloader

logger = logging.getLogger(__name__)


@dataclass
class DownloadJob:
    """Tracks progress of a download job."""

    status: str = "pending"  # pending | running | completed | failed | cancelled
    total_images: int = 0
    downloaded: int = 0
    failed: int = 0
    skipped: int = 0
    current_channel: str = ""
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DownloadManager:
    """Manages background image download jobs."""

    def __init__(self, database: Database, attachments_path: Path | None) -> None:
        self._database = database
        self._attachments_path = attachments_path
        self._job: DownloadJob | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def current_job(self) -> DownloadJob | None:
        return self._job

    @property
    def is_busy(self) -> bool:
        return self._job is not None and self._job.status in ("pending", "running")

    def start_download(self) -> DownloadJob:
        """Start a background download job.

        Returns:
            The created DownloadJob

        Raises:
            RuntimeError: If a download is already running or no attachments path
        """
        if self.is_busy:
            raise RuntimeError("A download is already running")
        if not self._attachments_path:
            raise RuntimeError("No attachments path configured")

        job = DownloadJob(started_at=datetime.now(UTC))
        self._job = job

        self._task = asyncio.create_task(self._run_download(job))
        return job

    def cancel(self) -> bool:
        """Request cancellation of the current download."""
        if not self.is_busy or self._job is None:
            return False
        if self._task and not self._task.done():
            self._task.cancel()
        return True

    async def _run_download(self, job: DownloadJob) -> None:
        """Execute the download in the background."""
        try:
            job.status = "running"
            logger.info("Download job started")

            downloader = ImageDownloader(
                database=self._database,
                output_dir=self._attachments_path,  # type: ignore[arg-type]
            )

            def progress_callback(channel_name: str, done: int, total: int) -> None:
                job.current_channel = channel_name
                # Update from downloader stats
                job.total_images = downloader.stats.total
                job.downloaded = downloader.stats.downloaded
                job.failed = downloader.stats.failed
                job.skipped = downloader.stats.skipped + downloader.stats.already_exists

            stats = await downloader.download_all_images(
                progress_callback=progress_callback
            )

            job.total_images = stats.total
            job.downloaded = stats.downloaded
            job.failed = stats.failed
            job.skipped = stats.skipped + stats.already_exists
            job.status = "completed"
            job.finished_at = datetime.now(UTC)
            logger.info(
                "Download completed: %d downloaded, %d failed, %d skipped",
                stats.downloaded,
                stats.failed,
                stats.skipped + stats.already_exists,
            )

        except asyncio.CancelledError:
            job.status = "cancelled"
            job.finished_at = datetime.now(UTC)
            logger.info("Download cancelled")

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.finished_at = datetime.now(UTC)
            logger.error("Download failed: %s", e)
