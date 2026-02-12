"""Download statistics API route handlers."""

from fastapi import APIRouter, Request

from sqlalchemy import func, select

from wumpus_archiver.api.routes._helpers import IMAGE_TYPES, get_attachments_path, get_db
from wumpus_archiver.api.schemas import DownloadChannelStats, DownloadStatsResponse
from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.message import Message

router = APIRouter()


@router.get("/downloads/stats", response_model=DownloadStatsResponse)
async def download_stats(request: Request) -> DownloadStatsResponse:
    """Get download statistics for image attachments."""
    db = get_db(request)
    attachments_path = get_attachments_path(request)

    async with db.session() as session:
        status_counts = await session.execute(
            select(Attachment.download_status, func.count(Attachment.id))
            .where(Attachment.content_type.in_(IMAGE_TYPES))
            .group_by(Attachment.download_status)
        )
        counts: dict[str, int] = {}
        for status, count in status_counts.all():
            counts[status] = count

        bytes_result = await session.execute(
            select(func.coalesce(func.sum(Attachment.size), 0))
            .where(Attachment.content_type.in_(IMAGE_TYPES))
            .where(Attachment.download_status == "downloaded")
        )
        downloaded_bytes = bytes_result.scalar() or 0

        channel_stats_result = await session.execute(
            select(
                Channel.id,
                Channel.name,
                Attachment.download_status,
                func.count(Attachment.id),
                func.coalesce(func.sum(Attachment.size), 0),
            )
            .join(Message, Message.channel_id == Channel.id)
            .join(Attachment, Attachment.message_id == Message.id)
            .where(Attachment.content_type.in_(IMAGE_TYPES))
            .group_by(Channel.id, Channel.name, Attachment.download_status)
            .order_by(Channel.name)
        )

        channel_map: dict[int, dict[str, object]] = {}
        for ch_id, ch_name, dl_status, count, byte_sum in channel_stats_result.all():
            if ch_id not in channel_map:
                channel_map[ch_id] = {
                    "channel_id": ch_id,
                    "channel_name": ch_name,
                    "downloaded": 0,
                    "pending": 0,
                    "failed": 0,
                    "skipped": 0,
                    "total_images": 0,
                    "downloaded_bytes": 0,
                }
            entry = channel_map[ch_id]
            entry["total_images"] = int(entry["total_images"]) + count  # type: ignore[arg-type]
            if dl_status == "downloaded":
                entry["downloaded"] = count
                entry["downloaded_bytes"] = byte_sum
            elif dl_status == "failed":
                entry["failed"] = count
            elif dl_status == "skipped":
                entry["skipped"] = count
            else:
                entry["pending"] = int(entry["pending"]) + count  # type: ignore[arg-type]

        channels_sorted = sorted(
            channel_map.values(),
            key=lambda c: c["total_images"],  # type: ignore[arg-type]
            reverse=True,
        )

        return DownloadStatsResponse(
            total_images=sum(counts.values()),
            downloaded=counts.get("downloaded", 0),
            pending=counts.get("pending", 0),
            failed=counts.get("failed", 0),
            skipped=counts.get("skipped", 0),
            downloaded_bytes=downloaded_bytes,
            attachments_dir=str(attachments_path) if attachments_path else None,
            channels=[DownloadChannelStats(**ch) for ch in channels_sorted],  # type: ignore[arg-type]
        )
