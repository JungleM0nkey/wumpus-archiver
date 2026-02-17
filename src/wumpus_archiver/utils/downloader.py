"""Image downloader for Discord attachments.

Downloads all image attachments from the archive database to local storage,
updates attachment records with local paths, and supports resumable downloads
with content hashing for deduplication.
"""

import asyncio
import hashlib
import logging
from pathlib import Path

import aiohttp
from sqlalchemy import or_, select, func

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.message import Message
from wumpus_archiver.storage.database import Database

logger = logging.getLogger(__name__)

IMAGE_CONTENT_TYPES = (
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/avif",
)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".tiff")


def _image_filter():
    """SQLAlchemy filter for image attachments (by content_type or file extension)."""
    return or_(
        Attachment.content_type.in_(IMAGE_CONTENT_TYPES),
        *[Attachment.filename.ilike(f"%{ext}") for ext in IMAGE_EXTENSIONS],
    )

# Default concurrency and retry settings
DEFAULT_CONCURRENCY = 5
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 2.0
DEFAULT_TIMEOUT = 60


def _sanitize_filename(filename: str) -> str:
    """Sanitize a filename for safe filesystem storage.

    Args:
        filename: Original filename from Discord

    Returns:
        Sanitized filename safe for local storage
    """
    # Replace path separators and other problematic chars
    for char in r'<>:"/\|?*':
        filename = filename.replace(char, "_")
    # Limit length to avoid filesystem issues
    if len(filename) > 200:
        stem = Path(filename).stem[:180]
        suffix = Path(filename).suffix
        filename = stem + suffix
    return filename


def _compute_hash(data: bytes) -> str:
    """Compute SHA-256 hash of file data.

    Args:
        data: File content bytes

    Returns:
        Hex-encoded SHA-256 hash
    """
    return hashlib.sha256(data).hexdigest()


class DownloadStats:
    """Track download progress statistics."""

    def __init__(self) -> None:
        self.total: int = 0
        self.downloaded: int = 0
        self.skipped: int = 0
        self.failed: int = 0
        self.already_exists: int = 0
        self.total_bytes: int = 0
        self.errors: list[str] = []

    @property
    def processed(self) -> int:
        """Total items processed."""
        return self.downloaded + self.skipped + self.failed + self.already_exists

    def summary(self) -> dict[str, object]:
        """Return summary as dict."""
        return {
            "total": self.total,
            "downloaded": self.downloaded,
            "skipped": self.skipped,
            "failed": self.failed,
            "already_exists": self.already_exists,
            "total_bytes": self.total_bytes,
            "errors": self.errors[:20],  # Cap errors in summary
        }


class ImageDownloader:
    """Async image downloader for Discord attachments.

    Downloads image attachments to a local directory structure organized by
    channel ID, updates the database with local paths, and supports resumable
    downloading (skips already-downloaded files).

    Args:
        database: Database instance for querying/updating attachments
        output_dir: Root directory for downloaded images
        concurrency: Max concurrent downloads
        max_retries: Max retries per failed download
        timeout: HTTP request timeout in seconds
    """

    def __init__(
        self,
        database: Database,
        output_dir: Path,
        concurrency: int = DEFAULT_CONCURRENCY,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.database = database
        self.output_dir = output_dir.resolve()
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.stats = DownloadStats()
        self._semaphore = asyncio.Semaphore(concurrency)

    async def download_guild_images(
        self,
        guild_id: int,
        progress_callback: "((str, int, int) -> None) | None" = None,
    ) -> DownloadStats:
        """Download all image attachments for a guild.

        Args:
            guild_id: Discord guild ID to download images for
            progress_callback: Optional callback(channel_name, done, total)

        Returns:
            Download statistics
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats = DownloadStats()

        async with self.database.session() as session:
            # Get all channels in the guild
            ch_result = await session.execute(
                select(Channel)
                .where(Channel.guild_id == guild_id)
                .order_by(Channel.position)
            )
            channels = ch_result.scalars().all()

        logger.info("Found %d channels in guild %d", len(channels), guild_id)

        for channel in channels:
            await self._download_channel_images(
                channel_id=channel.id,
                channel_name=channel.name,
                progress_callback=progress_callback,
            )

        return self.stats

    async def download_all_images(
        self,
        progress_callback: "((str, int, int) -> None) | None" = None,
    ) -> DownloadStats:
        """Download all image attachments in the database.

        Args:
            progress_callback: Optional callback(channel_name, done, total)

        Returns:
            Download statistics
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.stats = DownloadStats()

        async with self.database.session() as session:
            ch_result = await session.execute(
                select(Channel).order_by(Channel.guild_id, Channel.position)
            )
            channels = ch_result.scalars().all()

        logger.info("Found %d channels total", len(channels))

        for channel in channels:
            await self._download_channel_images(
                channel_id=channel.id,
                channel_name=channel.name,
                progress_callback=progress_callback,
            )

        return self.stats

    async def _download_channel_images(
        self,
        channel_id: int,
        channel_name: str,
        progress_callback: "((str, int, int) -> None) | None" = None,
    ) -> None:
        """Download all image attachments for a single channel.

        Args:
            channel_id: Channel ID to download images from
            channel_name: Human-readable channel name for logging
            progress_callback: Optional callback(channel_name, done, total)
        """
        # Create channel directory
        channel_dir = self.output_dir / str(channel_id)
        channel_dir.mkdir(parents=True, exist_ok=True)

        # Get image attachments for this channel
        async with self.database.session() as session:
            count_result = await session.execute(
                select(func.count(Attachment.id))
                .where(
                    Attachment.message_id.in_(
                        select(Message.id).where(Message.channel_id == channel_id)
                    )
                )
                .where(_image_filter())
            )
            total = count_result.scalar() or 0

        if total == 0:
            logger.debug("No images in channel #%s", channel_name)
            return

        logger.info("Channel #%s: %d images to process", channel_name, total)
        self.stats.total += total

        # Process in batches to avoid loading everything into memory
        batch_size = 100
        offset = 0
        channel_done = 0

        async with aiohttp.ClientSession(timeout=self.timeout) as http_session:
            while offset < total:
                async with self.database.session() as session:
                    result = await session.execute(
                        select(Attachment)
                        .where(
                            Attachment.message_id.in_(
                                select(Message.id).where(
                                    Message.channel_id == channel_id
                                )
                            )
                        )
                        .where(_image_filter())
                        .order_by(Attachment.id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                    attachments = list(result.scalars().all())

                if not attachments:
                    break

                # Download batch concurrently
                tasks = [
                    self._download_attachment(http_session, att, channel_dir)
                    for att in attachments
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results and update DB
                async with self.database.session() as session:
                    for att, download_result in zip(attachments, results):
                        if isinstance(download_result, Exception):
                            logger.error(
                                "Unexpected error for %s: %s",
                                att.filename,
                                download_result,
                            )
                            self.stats.failed += 1
                            self.stats.errors.append(
                                f"{att.filename}: {download_result}"
                            )
                            await self._update_attachment_status(
                                session, att.id, "failed", None, None
                            )
                        elif download_result is not None:
                            local_path, content_hash, size = download_result
                            await self._update_attachment_status(
                                session, att.id, "downloaded", local_path, content_hash
                            )
                            self.stats.downloaded += 1
                            self.stats.total_bytes += size
                        # None means skipped (already downloaded)

                    await session.commit()

                channel_done += len(attachments)
                if progress_callback:
                    progress_callback(channel_name, channel_done, total)

                offset += batch_size

    async def _download_attachment(
        self,
        http_session: aiohttp.ClientSession,
        attachment: Attachment,
        channel_dir: Path,
    ) -> "tuple[str, str, int] | None":
        """Download a single attachment.

        Args:
            http_session: aiohttp client session
            attachment: Attachment ORM object
            channel_dir: Directory to save files to

        Returns:
            Tuple of (relative_local_path, content_hash, size) or None if skipped
        """
        async with self._semaphore:
            # Skip if already downloaded and file exists
            if attachment.download_status == "downloaded" and attachment.local_path:
                full_path = self.output_dir / attachment.local_path
                if full_path.exists():
                    self.stats.already_exists += 1
                    return None

            # Build local file path: {channel_id}/{attachment_id}_{filename}
            safe_name = _sanitize_filename(attachment.filename)
            local_filename = f"{attachment.id}_{safe_name}"
            file_path = channel_dir / local_filename
            # Relative path from output_dir root for DB storage
            relative_path = str(file_path.relative_to(self.output_dir))

            # Try URL, then proxy_url as fallback
            urls_to_try = [attachment.url]
            if attachment.proxy_url:
                urls_to_try.append(attachment.proxy_url)

            for attempt in range(self.max_retries):
                for url in urls_to_try:
                    try:
                        async with http_session.get(url) as response:
                            if response.status == 200:
                                data = await response.read()
                                content_hash = _compute_hash(data)

                                # Write file
                                file_path.write_bytes(data)

                                logger.debug(
                                    "Downloaded %s (%d bytes)",
                                    attachment.filename,
                                    len(data),
                                )
                                return (relative_path, content_hash, len(data))

                            if response.status == 404:
                                logger.warning(
                                    "File not found (404): %s", attachment.filename
                                )
                                self.stats.skipped += 1
                                return None

                            logger.warning(
                                "HTTP %d for %s (attempt %d)",
                                response.status,
                                attachment.filename,
                                attempt + 1,
                            )

                    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                        logger.warning(
                            "Download error for %s (attempt %d): %s",
                            attachment.filename,
                            attempt + 1,
                            e,
                        )

                # Exponential backoff between retries
                if attempt < self.max_retries - 1:
                    delay = DEFAULT_RETRY_DELAY * (2 ** attempt)
                    await asyncio.sleep(delay)

            # All retries exhausted
            error_msg = f"Failed after {self.max_retries} retries: {attachment.filename}"
            logger.error(error_msg)
            self.stats.failed += 1
            self.stats.errors.append(error_msg)
            return None

    async def _update_attachment_status(
        self,
        session: "AsyncSession",  # type: ignore[name-defined]  # noqa: F821
        attachment_id: int,
        status: str,
        local_path: str | None,
        content_hash: str | None,
    ) -> None:
        """Update attachment download status in database.

        Args:
            session: Active database session
            attachment_id: Attachment ID to update
            status: New download status
            local_path: Relative path to local file
            content_hash: SHA-256 hash of file content
        """
        from sqlalchemy import update as sa_update

        stmt = (
            sa_update(Attachment)
            .where(Attachment.id == attachment_id)
            .values(
                download_status=status,
                local_path=local_path,
                content_hash=content_hash,
            )
        )
        await session.execute(stmt)
