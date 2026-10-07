"""Gallery API route handlers."""

import datetime as dt
from collections import OrderedDict

from fastapi import APIRouter, Query

from wumpus_archiver.api.deps import AttachmentsDir, Db
from wumpus_archiver.api.routes._helpers import rows_to_gallery_schemas
from wumpus_archiver.api.schemas import (
    GalleryResponse,
    TimelineGalleryGroup,
    TimelineGalleryResponse,
)
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import AttachmentRow, MediaKind, Scope

router = APIRouter()

# The guild gallery's ``content_type`` parameter; anything else silently means images.
_KIND_PARAMS = {"gif": MediaKind.GIF, "video": MediaKind.VIDEO}


@router.get("/channels/{channel_id}/gallery", response_model=GalleryResponse)
async def channel_gallery(
    db: Db,
    attachments_dir: AttachmentsDir,
    channel_id: int,
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(60, ge=1, le=200, description="Number of images to return"),
) -> GalleryResponse:
    """Get image attachments from a channel for gallery view."""
    async with db.session() as session:
        page = await archive_reads.attachments(
            session, Scope(channel=channel_id), kind=MediaKind.IMAGE, limit=limit, offset=offset
        )

    return GalleryResponse(
        attachments=rows_to_gallery_schemas(attachments_dir, page.rows, channel_names=False),
        total=page.total,
        has_more=page.has_more,
        offset=offset,
    )


@router.get("/guilds/{guild_id}/gallery", response_model=GalleryResponse)
async def guild_gallery(
    db: Db,
    attachments_dir: AttachmentsDir,
    guild_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    channel_id: int | None = Query(None, description="Filter by channel"),
    content_type: str | None = Query(None, description="Filter by type: image, gif, video"),
) -> GalleryResponse:
    """Get all image attachments across a guild, optionally filtered."""
    kind = _KIND_PARAMS.get(content_type or "", MediaKind.IMAGE)
    async with db.session() as session:
        page = await archive_reads.attachments(
            session,
            Scope(guild=guild_id, channel=channel_id),
            kind=kind,
            limit=limit,
            offset=offset,
        )

    return GalleryResponse(
        attachments=rows_to_gallery_schemas(attachments_dir, page.rows),
        total=page.total,
        has_more=page.has_more,
        offset=offset,
    )


def _period_label(date: dt.datetime, group_by: str) -> tuple[str, str]:
    """Derive period key and display label from a datetime.

    Args:
        date: Timestamp to classify
        group_by: Grouping strategy — "week", "month", or "year"

    Returns:
        Tuple of (period_key, human_label)
    """
    if group_by == "week":
        week_start = date - dt.timedelta(days=date.weekday())
        return week_start.strftime("%Y-W%W"), f"Week of {week_start.strftime('%b %d, %Y')}"
    elif group_by == "year":
        return date.strftime("%Y"), date.strftime("%Y")
    else:
        return date.strftime("%Y-%m"), date.strftime("%B %Y")


@router.get("/guilds/{guild_id}/gallery/timeline", response_model=TimelineGalleryResponse)
async def guild_gallery_timeline(
    db: Db,
    attachments_dir: AttachmentsDir,
    guild_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(120, ge=1, le=500),
    channel_id: int | None = Query(None, description="Filter by channel"),
    group_by: str = Query("month", description="Group by: week, month, year"),
) -> TimelineGalleryResponse:
    """Get guild images grouped by time period for timeline view."""
    async with db.session() as session:
        page = await archive_reads.attachments(
            session,
            Scope(guild=guild_id, channel=channel_id),
            kind=MediaKind.IMAGE,
            limit=limit,
            offset=offset,
        )

    # Grouping is page-local: it groups what is on this page, not the whole scope.
    groups: OrderedDict[str, list[AttachmentRow]] = OrderedDict()
    for row in page.rows:
        period, _label = _period_label(row.created_at, group_by)
        groups.setdefault(period, []).append(row)

    timeline_groups = []
    for period, group_rows in groups.items():
        att_schemas = rows_to_gallery_schemas(attachments_dir, group_rows)
        _period_key, label = _period_label(group_rows[0].created_at, group_by)
        timeline_groups.append(
            TimelineGalleryGroup(
                period=period,
                label=label,
                count=len(att_schemas),
                attachments=att_schemas,
            )
        )

    return TimelineGalleryResponse(
        groups=timeline_groups,
        total=page.total,
        has_more=page.has_more,
        offset=offset,
    )
