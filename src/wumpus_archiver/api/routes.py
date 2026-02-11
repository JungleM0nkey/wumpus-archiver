"""API route handlers."""

from pathlib import Path

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from wumpus_archiver.api.schemas import (
    AttachmentSchema,
    ChannelListResponse,
    ChannelSchema,
    DownloadChannelStats,
    DownloadStatsResponse,
    GalleryAttachmentSchema,
    GalleryResponse,
    GuildDetailSchema,
    GuildSchema,
    MessageListResponse,
    MessageSchema,
    ScrapeHistoryResponse,
    ScrapeJobSchema,
    ScrapeProgressSchema,
    ScrapeStartRequest,
    ScrapeStatusResponse,
    SearchResponse,
    SearchResultSchema,
    StatsSchema,
    TimelineGalleryGroup,
    TimelineGalleryResponse,
    UserChannelActivity,
    UserListItem,
    UserListResponse,
    UserMonthlyActivity,
    UserProfileSchema,
    UserSchema,
)
from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

router = APIRouter()


def _get_db(request: Request) -> Database:
    """Get database from app state."""
    return request.app.state.database  # type: ignore[no-any-return]


def _get_attachments_path(request: Request) -> Path | None:
    """Get local attachments path from app state."""
    return getattr(request.app.state, "attachments_path", None)


def _rewrite_attachment_url(
    request: Request,
    local_path: str | None,
    download_status: str,
    original_url: str,
) -> str:
    """Rewrite attachment URL to local version if downloaded.

    Args:
        request: Current request (for base URL)
        local_path: Relative local path from attachment record
        download_status: Download status of the attachment
        original_url: Original Discord CDN URL

    Returns:
        Local URL if downloaded, otherwise original URL
    """
    attachments_dir = _get_attachments_path(request)
    if (
        attachments_dir
        and local_path
        and download_status == "downloaded"
        and (attachments_dir / local_path).exists()
    ):
        return f"/attachments/{local_path}"
    return original_url


def _rewrite_attachment_schema(request: Request, schema: AttachmentSchema) -> AttachmentSchema:
    """Rewrite URLs in an AttachmentSchema if local file exists."""
    # We need to query the DB for local_path — but schemas don't have it.
    # Instead the caller should pass the ORM object data.
    return schema


@router.get("/guilds", response_model=list[GuildSchema])
async def list_guilds(request: Request) -> list[GuildSchema]:
    """List all archived guilds."""
    db = _get_db(request)
    async with db.session() as session:
        result = await session.execute(select(Guild))
        guilds = result.scalars().all()

        schemas = []
        for guild in guilds:
            # Count channels and messages
            ch_count = await session.execute(
                select(func.count(Channel.id)).where(Channel.guild_id == guild.id)
            )
            msg_count = await session.execute(
                select(func.count(Message.id)).where(
                    Message.channel_id.in_(
                        select(Channel.id).where(Channel.guild_id == guild.id)
                    )
                )
            )
            schema = GuildSchema.model_validate(guild)
            schema.channel_count = ch_count.scalar() or 0
            schema.message_count = msg_count.scalar() or 0
            schemas.append(schema)

        return schemas


@router.get("/guilds/{guild_id}", response_model=GuildDetailSchema)
async def get_guild(request: Request, guild_id: int) -> GuildDetailSchema:
    """Get guild details with channels."""
    db = _get_db(request)
    async with db.session() as session:
        result = await session.execute(
            select(Guild).where(Guild.id == guild_id)
        )
        guild = result.scalar_one_or_none()
        if not guild:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Guild not found")

        # Fetch channels ordered by position
        ch_result = await session.execute(
            select(Channel)
            .where(Channel.guild_id == guild_id)
            .order_by(Channel.position)
        )
        channels = ch_result.scalars().all()

        schema = GuildDetailSchema(
            **{k: v for k, v in guild.__dict__.items() if not k.startswith("_")}
        )
        schema.channels = [ChannelSchema.model_validate(ch) for ch in channels]
        schema.channel_count = len(channels)

        msg_count = await session.execute(
            select(func.count(Message.id)).where(
                Message.channel_id.in_(
                    select(Channel.id).where(Channel.guild_id == guild_id)
                )
            )
        )
        schema.message_count = msg_count.scalar() or 0

        return schema


@router.get("/guilds/{guild_id}/channels", response_model=ChannelListResponse)
async def list_channels(request: Request, guild_id: int) -> ChannelListResponse:
    """List channels for a guild."""
    db = _get_db(request)
    async with db.session() as session:
        result = await session.execute(
            select(Channel)
            .where(Channel.guild_id == guild_id)
            .order_by(Channel.position)
        )
        channels = result.scalars().all()
        return ChannelListResponse(
            channels=[ChannelSchema.model_validate(ch) for ch in channels],
            total=len(channels),
        )


@router.get("/channels/{channel_id}/gallery", response_model=GalleryResponse)
async def channel_gallery(
    request: Request,
    channel_id: int,
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(60, ge=1, le=200, description="Number of images to return"),
) -> GalleryResponse:
    """Get image attachments from a channel for gallery view."""
    db = _get_db(request)
    image_types = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/avif")
    async with db.session() as session:
        # Query image attachments joined with message + author
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
            .where(Attachment.content_type.in_(image_types))
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )

        result = await session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Total count
        count_result = await session.execute(
            select(func.count(Attachment.id))
            .where(Attachment.message_id.in_(
                select(Message.id).where(Message.channel_id == channel_id)
            ))
            .where(Attachment.content_type.in_(image_types))
        )
        total = count_result.scalar() or 0

        attachments = _rows_to_gallery_schemas(request, rows)

        return GalleryResponse(
            attachments=attachments,
            total=total,
            has_more=has_more,
            offset=offset,
        )


def _rows_to_gallery_schemas(
    request: Request,
    rows: list[tuple],  # type: ignore[type-arg]
    channel_map: dict[int, str] | None = None,
) -> list[GalleryAttachmentSchema]:
    """Convert raw DB rows to GalleryAttachmentSchema list.

    Args:
        request: Current request for URL rewriting
        rows: Tuples of (Attachment, created_at, channel_id, username, global_name, avatar_url)
        channel_map: Optional map of channel_id -> channel_name

    Returns:
        List of GalleryAttachmentSchema
    """
    attachments = []
    for att, created_at, msg_channel_id, username, global_name, avatar_url in rows:
        url = _rewrite_attachment_url(
            request, att.local_path, att.download_status, att.url
        )
        proxy_url = att.proxy_url
        if url != att.url:
            proxy_url = None
        attachments.append(
            GalleryAttachmentSchema(
                id=att.id,
                message_id=att.message_id,
                filename=att.filename,
                content_type=att.content_type,
                size=att.size,
                url=url,
                proxy_url=proxy_url,
                width=att.width,
                height=att.height,
                created_at=created_at,
                author_name=global_name or username,
                author_avatar_url=avatar_url,
                channel_id=msg_channel_id,
                channel_name=channel_map.get(msg_channel_id) if channel_map else None,
            )
        )
    return attachments


IMAGE_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/avif")


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
    db = _get_db(request)
    guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

    # Determine content type filter
    if content_type == "gif":
        type_filter = ("image/gif",)
    elif content_type == "video":
        type_filter = ("video/mp4", "video/webm", "video/quicktime")
    else:
        type_filter = IMAGE_TYPES

    async with db.session() as session:
        # Build base filter on messages belonging to this guild
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
            .where(Attachment.content_type.in_(type_filter))
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )

        result = await session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Total count
        count_result = await session.execute(
            select(func.count(Attachment.id))
            .where(Attachment.message_id.in_(msg_filter))
            .where(Attachment.content_type.in_(type_filter))
        )
        total = count_result.scalar() or 0

        # Get channel names
        ch_ids = {r[2] for r in rows}
        ch_result = await session.execute(
            select(Channel.id, Channel.name).where(Channel.id.in_(ch_ids))
        )
        ch_map = dict(ch_result.all())

        attachments = _rows_to_gallery_schemas(request, rows, ch_map)

        return GalleryResponse(
            attachments=attachments,
            total=total,
            has_more=has_more,
            offset=offset,
        )


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
    db = _get_db(request)
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
            .where(Attachment.content_type.in_(IMAGE_TYPES))
            .order_by(Message.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )

        result = await session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Total count
        count_result = await session.execute(
            select(func.count(Attachment.id))
            .where(Attachment.message_id.in_(msg_filter))
            .where(Attachment.content_type.in_(IMAGE_TYPES))
        )
        total = count_result.scalar() or 0

        # Get channel names
        ch_ids = {r[2] for r in rows}
        ch_result = await session.execute(
            select(Channel.id, Channel.name).where(Channel.id.in_(ch_ids))
        )
        ch_map = dict(ch_result.all())

        # Group by time period
        from collections import OrderedDict

        groups: OrderedDict[str, list[tuple]] = OrderedDict()  # type: ignore[type-arg]
        for row in rows:
            att, created_at, *_ = row
            dt = created_at
            if group_by == "week":
                # ISO week start (Monday)
                week_start = dt - __import__("datetime").timedelta(days=dt.weekday())
                period = week_start.strftime("%Y-W%W")
                label = f"Week of {week_start.strftime('%b %d, %Y')}"
            elif group_by == "year":
                period = dt.strftime("%Y")
                label = dt.strftime("%Y")
            else:
                period = dt.strftime("%Y-%m")
                label = dt.strftime("%B %Y")

            if period not in groups:
                groups[period] = []
            groups[period].append(row)

        timeline_groups = []
        for period, group_rows in groups.items():
            att_schemas = _rows_to_gallery_schemas(request, group_rows, ch_map)
            # Derive label from the first row
            dt = group_rows[0][1]
            if group_by == "week":
                week_start = dt - __import__("datetime").timedelta(days=dt.weekday())
                label = f"Week of {week_start.strftime('%b %d, %Y')}"
            elif group_by == "year":
                label = dt.strftime("%Y")
            else:
                label = dt.strftime("%B %Y")

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


@router.get("/channels/{channel_id}/messages", response_model=MessageListResponse)
async def list_messages(
    request: Request,
    channel_id: int,
    before: int | None = Query(None, description="Get messages before this ID"),
    after: int | None = Query(None, description="Get messages after this ID"),
    limit: int = Query(50, ge=1, le=200, description="Number of messages to return"),
) -> MessageListResponse:
    """Get messages from a channel with pagination."""
    db = _get_db(request)
    async with db.session() as session:
        query = (
            select(Message)
            .where(Message.channel_id == channel_id)
            .options(
                selectinload(Message.author),
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .order_by(Message.created_at.asc())
            .limit(limit + 1)  # Fetch one extra to check has_more
        )

        if before:
            query = query.where(Message.id < before)
        if after:
            query = query.where(Message.id > after)

        result = await session.execute(query)
        messages = list(result.scalars().all())

        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]

        # Get total count for channel
        total_result = await session.execute(
            select(func.count(Message.id)).where(Message.channel_id == channel_id)
        )
        total = total_result.scalar() or 0

        schemas = []
        for msg in messages:
            schema = MessageSchema.model_validate(msg)
            if msg.author:
                author_schema = UserSchema.model_validate(msg.author)
                author_schema.display_name = msg.author.display_name
                schema.author = author_schema
            # Rewrite attachment URLs to local versions if downloaded
            for att_orm, att_schema in zip(msg.attachments, schema.attachments):
                rewritten = _rewrite_attachment_url(
                    request,
                    att_orm.local_path,
                    att_orm.download_status,
                    att_orm.url,
                )
                if rewritten != att_orm.url:
                    att_schema.url = rewritten
                    att_schema.proxy_url = None
            schemas.append(schema)

        return MessageListResponse(
            messages=schemas,
            total=total,
            has_more=has_more,
            before_id=messages[0].id if messages else None,
            after_id=messages[-1].id if messages else None,
        )


@router.get("/search", response_model=SearchResponse)
async def search_messages(
    request: Request,
    q: str = Query(..., min_length=1, description="Search query"),
    guild_id: int | None = Query(None, description="Filter by guild"),
    channel_id: int | None = Query(None, description="Filter by channel"),
    author_id: int | None = Query(None, description="Filter by author"),
    limit: int = Query(50, ge=1, le=100, description="Max results"),
) -> SearchResponse:
    """Search messages by content."""
    db = _get_db(request)
    async with db.session() as session:
        query = (
            select(Message)
            .options(
                selectinload(Message.author),
                selectinload(Message.attachments),
                selectinload(Message.reactions),
            )
            .where(Message.content.ilike(f"%{q}%"))
            .order_by(Message.created_at.desc())
            .limit(limit)
        )

        if channel_id:
            query = query.where(Message.channel_id == channel_id)
        elif guild_id:
            query = query.where(
                Message.channel_id.in_(
                    select(Channel.id).where(Channel.guild_id == guild_id)
                )
            )
        if author_id:
            query = query.where(Message.author_id == author_id)

        result = await session.execute(query)
        messages = list(result.scalars().all())

        # Get channel names for results
        channel_ids = {m.channel_id for m in messages}
        ch_result = await session.execute(
            select(Channel).where(Channel.id.in_(channel_ids))
        )
        channel_map = {ch.id: ch.name for ch in ch_result.scalars().all()}

        # Count total matches
        count_query = select(func.count(Message.id)).where(
            Message.content.ilike(f"%{q}%")
        )
        if channel_id:
            count_query = count_query.where(Message.channel_id == channel_id)
        elif guild_id:
            count_query = count_query.where(
                Message.channel_id.in_(
                    select(Channel.id).where(Channel.guild_id == guild_id)
                )
            )
        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        results = []
        for msg in messages:
            msg_schema = MessageSchema.model_validate(msg)
            if msg.author:
                author_schema = UserSchema.model_validate(msg.author)
                author_schema.display_name = msg.author.display_name
                msg_schema.author = author_schema
            # Rewrite attachment URLs to local versions if downloaded
            for att_orm, att_schema in zip(msg.attachments, msg_schema.attachments):
                rewritten = _rewrite_attachment_url(
                    request,
                    att_orm.local_path,
                    att_orm.download_status,
                    att_orm.url,
                )
                if rewritten != att_orm.url:
                    att_schema.url = rewritten
                    att_schema.proxy_url = None

            results.append(
                SearchResultSchema(
                    message=msg_schema,
                    channel_name=channel_map.get(msg.channel_id, "unknown"),
                )
            )

        return SearchResponse(results=results, total=total, query=q)


@router.get("/guilds/{guild_id}/stats", response_model=StatsSchema)
async def get_guild_stats(request: Request, guild_id: int) -> StatsSchema:
    """Get statistics for a guild."""
    db = _get_db(request)
    async with db.session() as session:
        # Guild info
        guild_result = await session.execute(select(Guild).where(Guild.id == guild_id))
        guild = guild_result.scalar_one_or_none()
        if not guild:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Guild not found")

        guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

        # Total channels
        ch_count = await session.execute(
            select(func.count(Channel.id)).where(Channel.guild_id == guild_id)
        )

        # Total messages
        msg_count = await session.execute(
            select(func.count(Message.id)).where(
                Message.channel_id.in_(guild_channels)
            )
        )

        # Total unique users
        user_count = await session.execute(
            select(func.count(func.distinct(Message.author_id))).where(
                Message.channel_id.in_(guild_channels)
            )
        )

        # Total attachments
        att_count = await session.execute(
            select(func.count(Attachment.id)).where(
                Attachment.message_id.in_(
                    select(Message.id).where(Message.channel_id.in_(guild_channels))
                )
            )
        )

        # Top channels by message count
        top_ch_result = await session.execute(
            select(Channel.name, Channel.message_count)
            .where(Channel.guild_id == guild_id)
            .order_by(Channel.message_count.desc())
            .limit(10)
        )
        top_channels = [
            {"name": name, "message_count": count}
            for name, count in top_ch_result.all()
        ]

        # Top users by message count
        top_user_result = await session.execute(
            select(User.id, User.username, User.global_name, User.avatar_url, func.count(Message.id).label("count"))
            .join(Message, Message.author_id == User.id)
            .where(Message.channel_id.in_(guild_channels))
            .group_by(User.id, User.username, User.global_name, User.avatar_url)
            .order_by(func.count(Message.id).desc())
            .limit(10)
        )
        top_users = [
            {
                "id": str(uid),
                "username": username,
                "display_name": global_name or username,
                "avatar_url": avatar_url,
                "message_count": count,
            }
            for uid, username, global_name, avatar_url, count in top_user_result.all()
        ]

        return StatsSchema(
            guild_name=guild.name,
            total_channels=ch_count.scalar() or 0,
            total_messages=msg_count.scalar() or 0,
            total_users=user_count.scalar() or 0,
            total_attachments=att_count.scalar() or 0,
            top_channels=top_channels,
            top_users=top_users,
        )


@router.get("/users/{user_id}", response_model=UserSchema)
async def get_user(request: Request, user_id: int) -> UserSchema:
    """Get user details."""
    db = _get_db(request)
    async with db.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="User not found")

        schema = UserSchema.model_validate(user)
        schema.display_name = user.display_name
        return schema


@router.get("/guilds/{guild_id}/users", response_model=UserListResponse)
async def list_guild_users(
    request: Request,
    guild_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("messages", description="Sort by: messages, name, recent"),
    q: str | None = Query(None, description="Search by username"),
) -> UserListResponse:
    """List users who have posted in a guild, with message counts."""
    db = _get_db(request)
    guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

    async with db.session() as session:
        # Base query: users with message counts in this guild
        base = (
            select(
                User,
                func.count(Message.id).label("message_count"),
                func.min(Message.created_at).label("first_seen"),
                func.max(Message.created_at).label("last_seen"),
            )
            .join(Message, Message.author_id == User.id)
            .where(Message.channel_id.in_(guild_channels))
            .group_by(User.id)
        )

        if q:
            base = base.where(
                User.username.ilike(f"%{q}%") | User.global_name.ilike(f"%{q}%")
            )

        # Sorting
        if sort == "name":
            base = base.order_by(User.username.asc())
        elif sort == "recent":
            base = base.order_by(func.max(Message.created_at).desc())
        else:
            base = base.order_by(func.count(Message.id).desc())

        # Count total
        from sqlalchemy import literal_column
        count_q = select(func.count()).select_from(base.subquery())
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

        # Paginate
        query = base.offset(offset).limit(limit + 1)
        result = await session.execute(query)
        rows = result.all()

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        users = []
        for user, msg_count, first_seen, last_seen in rows:
            item = UserListItem(
                id=user.id,
                username=user.username,
                discriminator=user.discriminator,
                global_name=user.global_name,
                avatar_url=user.avatar_url,
                bot=user.bot,
                display_name=user.global_name or user.username,
                message_count=msg_count,
                first_seen=first_seen,
                last_seen=last_seen,
            )
            users.append(item)

        return UserListResponse(
            users=users,
            total=total,
            has_more=has_more,
            offset=offset,
        )


@router.get("/users/{user_id}/profile", response_model=UserProfileSchema)
async def get_user_profile(
    request: Request,
    user_id: int,
    guild_id: int | None = Query(None, description="Scope stats to a guild"),
) -> UserProfileSchema:
    """Get detailed user profile with statistics."""
    db = _get_db(request)
    async with db.session() as session:
        # Fetch user
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="User not found")

        # Scope messages to guild if specified
        if guild_id:
            guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)
            msg_scope = Message.channel_id.in_(guild_channels)
        else:
            msg_scope = True  # type: ignore[assignment]

        user_msgs = select(Message).where(
            Message.author_id == user_id,
            msg_scope,
        ).subquery()

        # Total messages
        total_msgs_r = await session.execute(
            select(func.count()).select_from(user_msgs)
        )
        total_messages = total_msgs_r.scalar() or 0

        # Total attachments
        total_att_r = await session.execute(
            select(func.count(Attachment.id)).where(
                Attachment.message_id.in_(select(user_msgs.c.id))
            )
        )
        total_attachments = total_att_r.scalar() or 0

        # Total reactions received
        total_reactions_r = await session.execute(
            select(func.coalesce(func.sum(Reaction.count), 0)).where(
                Reaction.message_id.in_(select(user_msgs.c.id))
            )
        )
        total_reactions_received = total_reactions_r.scalar() or 0

        # First / last message timestamps
        time_r = await session.execute(
            select(
                func.min(user_msgs.c.created_at),
                func.max(user_msgs.c.created_at),
            )
        )
        first_msg_at, last_msg_at = time_r.one()

        # Average message length
        avg_len_r = await session.execute(
            select(func.avg(func.length(user_msgs.c.content)))
        )
        avg_message_length = round(float(avg_len_r.scalar() or 0), 1)

        # Active channels count
        active_ch_r = await session.execute(
            select(func.count(func.distinct(user_msgs.c.channel_id)))
        )
        active_channels = active_ch_r.scalar() or 0

        # Top channels
        top_ch_r = await session.execute(
            select(
                Channel.id,
                Channel.name,
                func.count(Message.id).label("cnt"),
            )
            .join(Message, Message.channel_id == Channel.id)
            .where(Message.author_id == user_id, msg_scope)
            .group_by(Channel.id, Channel.name)
            .order_by(func.count(Message.id).desc())
            .limit(10)
        )
        top_channels = [
            UserChannelActivity(
                channel_id=ch_id,
                channel_name=ch_name,
                message_count=cnt,
            )
            for ch_id, ch_name, cnt in top_ch_r.all()
        ]

        # Monthly activity (last 24 months)
        import datetime as dt

        cutoff = dt.datetime.utcnow() - dt.timedelta(days=730)
        monthly_r = await session.execute(
            select(
                func.strftime("%Y-%m", Message.created_at).label("period"),
                func.count(Message.id).label("cnt"),
            )
            .where(
                Message.author_id == user_id,
                msg_scope,
                Message.created_at >= cutoff,
            )
            .group_by("period")
            .order_by("period")
        )
        monthly_activity = []
        for period, cnt in monthly_r.all():
            try:
                label = dt.datetime.strptime(period, "%Y-%m").strftime("%b %Y")
            except (ValueError, TypeError):
                label = str(period)
            monthly_activity.append(
                UserMonthlyActivity(period=period, label=label, count=cnt)
            )

        # Top reactions received on user's messages
        top_react_r = await session.execute(
            select(
                Reaction.emoji_name,
                func.sum(Reaction.count).label("total"),
            )
            .where(Reaction.message_id.in_(select(user_msgs.c.id)))
            .group_by(Reaction.emoji_name)
            .order_by(func.sum(Reaction.count).desc())
            .limit(10)
        )
        top_reactions_received = [
            {"emoji": name or "?", "count": int(total)}
            for name, total in top_react_r.all()
        ]

        return UserProfileSchema(
            id=user.id,
            username=user.username,
            discriminator=user.discriminator,
            global_name=user.global_name,
            avatar_url=user.avatar_url,
            bot=user.bot,
            display_name=user.global_name or user.username,
            total_messages=total_messages,
            total_attachments=total_attachments,
            total_reactions_received=total_reactions_received,
            first_message_at=first_msg_at,
            last_message_at=last_msg_at,
            active_channels=active_channels,
            avg_message_length=avg_message_length,
            top_channels=top_channels,
            monthly_activity=monthly_activity,
            top_reactions_received=top_reactions_received,
        )


# ---------------------------------------------------------------------------
#  Scrape Control Panel endpoints
# ---------------------------------------------------------------------------


def _get_scrape_manager(request: Request):  # type: ignore[no-untyped-def]
    """Get the scrape job manager from app state."""
    return request.app.state.scrape_manager


def _job_to_schema(job) -> ScrapeJobSchema:  # type: ignore[no-untyped-def]
    """Convert a ScrapeJob model to a response schema."""
    duration: float | None = None
    if job.started_at and job.completed_at:
        duration = (job.completed_at - job.started_at).total_seconds()
    elif job.started_at:
        from datetime import UTC, datetime

        duration = (datetime.now(UTC) - job.started_at).total_seconds()

    return ScrapeJobSchema(
        id=job.id,
        guild_id=job.guild_id,
        status=job.status.value,
        progress=ScrapeProgressSchema(
            current_channel=job.progress.current_channel,
            channels_done=job.progress.channels_done,
            messages_scraped=job.progress.messages_scraped,
            attachments_found=job.progress.attachments_found,
            errors=job.progress.errors,
        ),
        started_at=job.started_at.isoformat() if job.started_at else None,
        completed_at=job.completed_at.isoformat() if job.completed_at else None,
        result=job.result,
        error_message=job.error_message,
        duration_seconds=round(duration, 1) if duration is not None else None,
    )


@router.get("/scrape/status", response_model=ScrapeStatusResponse)
async def scrape_status(request: Request) -> ScrapeStatusResponse:
    """Get current scrape job status."""
    manager = _get_scrape_manager(request)
    has_token = getattr(request.app.state, "discord_token", None) is not None

    if manager.current_job is not None:
        return ScrapeStatusResponse(
            busy=manager.is_busy,
            current_job=_job_to_schema(manager.current_job),
            has_token=has_token,
        )

    return ScrapeStatusResponse(busy=False, has_token=has_token)


@router.post("/scrape/start")
async def scrape_start(request: Request, body: ScrapeStartRequest) -> JSONResponse:
    """Start a new scrape job."""
    manager = _get_scrape_manager(request)
    token = getattr(request.app.state, "discord_token", None)

    if not token:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No Discord bot token configured. "
                "Set DISCORD_BOT_TOKEN in .env or environment."
            },
        )

    if manager.is_busy:
        return JSONResponse(
            status_code=409,
            content={"error": "A scrape job is already running"},
        )

    job = manager.start_scrape(body.guild_id, token)
    return JSONResponse(
        status_code=202,
        content={"job": _job_to_schema(job).model_dump()},
    )


@router.post("/scrape/cancel")
async def scrape_cancel(request: Request) -> JSONResponse:
    """Cancel the current scrape job."""
    manager = _get_scrape_manager(request)

    if manager.cancel():
        return JSONResponse(content={"message": "Cancellation requested"})

    return JSONResponse(
        status_code=404,
        content={"error": "No running job to cancel"},
    )


@router.get("/scrape/history", response_model=ScrapeHistoryResponse)
async def scrape_history(request: Request) -> ScrapeHistoryResponse:
    """Get scrape job history."""
    manager = _get_scrape_manager(request)
    return ScrapeHistoryResponse(
        jobs=[_job_to_schema(j) for j in manager.history],
    )


# --- Download stats ---

IMAGE_CONTENT_TYPES = ("image/png", "image/jpeg", "image/gif", "image/webp", "image/avif")


@router.get("/downloads/stats", response_model=DownloadStatsResponse)
async def download_stats(request: Request) -> DownloadStatsResponse:
    """Get download statistics for image attachments."""
    db = _get_db(request)
    attachments_path = _get_attachments_path(request)

    async with db.session() as session:
        # Overall counts by download_status for image attachments only
        status_counts = await session.execute(
            select(Attachment.download_status, func.count(Attachment.id))
            .where(Attachment.content_type.in_(IMAGE_CONTENT_TYPES))
            .group_by(Attachment.download_status)
        )
        counts: dict[str, int] = {}
        for status, count in status_counts.all():
            counts[status] = count

        # Total downloaded bytes (sum of size for downloaded images)
        bytes_result = await session.execute(
            select(func.coalesce(func.sum(Attachment.size), 0))
            .where(Attachment.content_type.in_(IMAGE_CONTENT_TYPES))
            .where(Attachment.download_status == "downloaded")
        )
        downloaded_bytes = bytes_result.scalar() or 0

        # Per-channel breakdown
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
            .where(Attachment.content_type.in_(IMAGE_CONTENT_TYPES))
            .group_by(Channel.id, Channel.name, Attachment.download_status)
            .order_by(Channel.name)
        )

        # Aggregate per channel
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
            else:  # pending or any other
                entry["pending"] = int(entry["pending"]) + count  # type: ignore[arg-type]

        # Sort by total_images desc
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
