"""Gallery API route handlers."""

import datetime as dt
from collections import OrderedDict

from fastapi import APIRouter, Query, Request

from sqlalchemy import func, select

from wumpus_archiver.api.routes._helpers import (
    get_db,
    image_filter,
    rows_to_gallery_schemas,
)
from wumpus_archiver.api.schemas import (
    GalleryResponse,
    TimelineGalleryGroup,
    TimelineGalleryResponse,
)
from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User

router = APIRouter()


@router.get("/channels/{channel_id}/gallery", response_model=GalleryResponse)
async def channel_gallery(
    request: Request,
    channel_id: int,
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(60, ge=1, le=200, description="Number of images to return"),
) -> GalleryResponse:
    """Get image attachments from a channel for gallery view."""
    db = get_db(request)
    async with db.session() as session:
        query = (
            select(
                Attachment,
                Message.created_at,
                Message.channel_id,
                User.username,
                User.global_name,
                User.avatar_url,
            )
            .join(Message, Attachment.message_id == Message.id)
            .outerjoin(User, Message.author_id == User.id)
            .where(Attachment.message_id.in_(
                select(Message.id).where(Message.channel_id == channel_id)
            ))
            .where(image_filter())
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )

        result = await session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        count_result = await session.execute(
            select(func.count(Attachment.id))
            .where(Attachment.message_id.in_(
                select(Message.id).where(Message.channel_id == channel_id)
            ))
            .where(image_filter())
        )
        total = count_result.scalar() or 0

        attachments = rows_to_gallery_schemas(request, rows)

        return GalleryResponse(
            attachments=attachments,
            total=total,
            has_more=has_more,
            offset=offset,
        )


@router.get("/guilds/{guild_id}/gallery", response_model=GalleryResponse)
async def guild_gallery(
    request: Request,
    guild_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=200),
    channel_id: int | None = Query(None, description="Filter by channel"),
    content_type: str | None = Query(None, description="Filter by type: image, gif, video"),
) -> GalleryResponse:
    """Get all image attachments across a guild, optionally filtered."""
    db = get_db(request)
    guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

    if content_type == "gif":
        att_filter = Attachment.content_type == "image/gif"
    elif content_type == "video":
        att_filter = Attachment.content_type.in_(("video/mp4", "video/webm", "video/quicktime"))
    else:
        att_filter = image_filter()

    async with db.session() as session:
        msg_filter = select(Message.id).where(Message.channel_id.in_(guild_channels))
        if channel_id:
            msg_filter = select(Message.id).where(Message.channel_id == channel_id)

        query = (
            select(
                Attachment,
                Message.created_at,
                Message.channel_id,
                User.username,
                User.global_name,
                User.avatar_url,
            )
            .join(Message, Attachment.message_id == Message.id)
            .outerjoin(User, Message.author_id == User.id)
            .where(Attachment.message_id.in_(msg_filter))
            .where(att_filter)
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )

        result = await session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        count_result = await session.execute(
            select(func.count(Attachment.id))
            .where(Attachment.message_id.in_(msg_filter))
            .where(att_filter)
        )
        total = count_result.scalar() or 0

        ch_ids = {r[2] for r in rows}
        ch_result = await session.execute(
            select(Channel.id, Channel.name).where(Channel.id.in_(ch_ids))
        )
        ch_map = dict(ch_result.all())

        attachments = rows_to_gallery_schemas(request, rows, ch_map)

        return GalleryResponse(
            attachments=attachments,
            total=total,
            has_more=has_more,
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
    request: Request,
    guild_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(120, ge=1, le=500),
    channel_id: int | None = Query(None, description="Filter by channel"),
    group_by: str = Query("month", description="Group by: week, month, year"),
) -> TimelineGalleryResponse:
    """Get guild images grouped by time period for timeline view."""
    db = get_db(request)
    guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

    async with db.session() as session:
        msg_filter = select(Message.id).where(Message.channel_id.in_(guild_channels))
        if channel_id:
            msg_filter = select(Message.id).where(Message.channel_id == channel_id)

        query = (
            select(
                Attachment,
                Message.created_at,
                Message.channel_id,
                User.username,
                User.global_name,
                User.avatar_url,
            )
            .join(Message, Attachment.message_id == Message.id)
            .outerjoin(User, Message.author_id == User.id)
            .where(Attachment.message_id.in_(msg_filter))
            .where(image_filter())
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )

        result = await session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        count_result = await session.execute(
            select(func.count(Attachment.id))
            .where(Attachment.message_id.in_(msg_filter))
            .where(image_filter())
        )
        total = count_result.scalar() or 0

        ch_ids = {r[2] for r in rows}
        ch_result = await session.execute(
            select(Channel.id, Channel.name).where(Channel.id.in_(ch_ids))
        )
        ch_map = dict(ch_result.all())

        # Group by time period
        groups: OrderedDict[str, list[tuple]] = OrderedDict()  # type: ignore[type-arg]
        for row in rows:
            att, created_at, *_ = row
            period, _label = _period_label(created_at, group_by)
            if period not in groups:
                groups[period] = []
            groups[period].append(row)

        timeline_groups = []
        for period, group_rows in groups.items():
            att_schemas = rows_to_gallery_schemas(request, group_rows, ch_map)
            _period_key, label = _period_label(group_rows[0][1], group_by)
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
            total=total,
            has_more=has_more,
            offset=offset,
        )
