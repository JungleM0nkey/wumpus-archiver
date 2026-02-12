"""User API route handlers."""

import datetime as dt

from fastapi import APIRouter, Query, Request

from sqlalchemy import func, select

from wumpus_archiver.api.routes._helpers import get_db, raise_not_found
from wumpus_archiver.api.schemas import (
    UserChannelActivity,
    UserListItem,
    UserListResponse,
    UserMonthlyActivity,
    UserProfileSchema,
    UserSchema,
)
from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User

router = APIRouter()


@router.get("/users/{user_id}", response_model=UserSchema)
async def get_user(request: Request, user_id: int) -> UserSchema:
    """Get user details."""
    db = get_db(request)
    async with db.session() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise_not_found("User not found")

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
    db = get_db(request)
    guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

    async with db.session() as session:
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

        if sort == "name":
            base = base.order_by(User.username.asc())
        elif sort == "recent":
            base = base.order_by(func.max(Message.created_at).desc())
        else:
            base = base.order_by(func.count(Message.id).desc())

        count_q = select(func.count()).select_from(base.subquery())
        total_result = await session.execute(count_q)
        total = total_result.scalar() or 0

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
    db = get_db(request)
    async with db.session() as session:
        user_result = await session.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if not user:
            raise_not_found("User not found")

        if guild_id:
            guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)
            msg_scope = Message.channel_id.in_(guild_channels)
        else:
            msg_scope = True  # type: ignore[assignment]

        user_msgs = select(Message).where(
            Message.author_id == user_id,
            msg_scope,
        ).subquery()

        total_msgs_r = await session.execute(
            select(func.count()).select_from(user_msgs)
        )
        total_messages = total_msgs_r.scalar() or 0

        total_att_r = await session.execute(
            select(func.count(Attachment.id)).where(
                Attachment.message_id.in_(select(user_msgs.c.id))
            )
        )
        total_attachments = total_att_r.scalar() or 0

        total_reactions_r = await session.execute(
            select(func.coalesce(func.sum(Reaction.count), 0)).where(
                Reaction.message_id.in_(select(user_msgs.c.id))
            )
        )
        total_reactions_received = total_reactions_r.scalar() or 0

        time_r = await session.execute(
            select(
                func.min(user_msgs.c.created_at),
                func.max(user_msgs.c.created_at),
            )
        )
        first_msg_at, last_msg_at = time_r.one()

        avg_len_r = await session.execute(
            select(func.avg(func.length(user_msgs.c.content)))
        )
        avg_message_length = round(float(avg_len_r.scalar() or 0), 1)

        active_ch_r = await session.execute(
            select(func.count(func.distinct(user_msgs.c.channel_id)))
        )
        active_channels = active_ch_r.scalar() or 0

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

        cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=730)
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
