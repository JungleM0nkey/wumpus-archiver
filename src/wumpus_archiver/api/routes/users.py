"""User API route handlers."""

import datetime as dt

from fastapi import APIRouter, Query

from wumpus_archiver.api.deps import Db
from wumpus_archiver.api.routes._helpers import raise_not_found
from wumpus_archiver.api.schemas import (
    UserChannelActivity,
    UserListItem,
    UserListResponse,
    UserMonthlyActivity,
    UserProfileSchema,
    UserSchema,
)
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import AuthorSort, Period, Scope

router = APIRouter()

# How far back the profile's monthly activity reaches.
ACTIVITY_WINDOW = dt.timedelta(days=730)


@router.get("/users/{user_id}", response_model=UserSchema)
async def get_user(db: Db, user_id: int) -> UserSchema:
    """Get user details."""
    async with db.session() as session:
        user = await archive_reads.user(session, user_id)
        if not user:
            raise_not_found("User not found")

        schema = UserSchema.model_validate(user)
        schema.display_name = user.display_name
        return schema


@router.get("/guilds/{guild_id}/users", response_model=UserListResponse)
async def list_guild_users(
    db: Db,
    guild_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    sort: str = Query("messages", description="Sort by: messages, name, recent"),
    q: str | None = Query(None, description="Search by username"),
) -> UserListResponse:
    """List users who have posted in a guild, with message counts."""
    try:
        author_sort = AuthorSort(sort)
    except ValueError:
        author_sort = AuthorSort.MESSAGES

    async with db.session() as session:
        page = await archive_reads.authors(
            session,
            Scope(guild=guild_id),
            sort=author_sort,
            limit=limit,
            offset=offset,
            name=q or None,
        )

    users = [
        UserListItem(
            id=row.user.id,
            username=row.user.username,
            discriminator=row.user.discriminator,
            global_name=row.user.global_name,
            avatar_url=row.user.avatar_url,
            bot=row.user.bot,
            display_name=row.user.global_name or row.user.username,
            message_count=row.messages,
            first_seen=row.first_seen,
            last_seen=row.last_seen,
        )
        for row in page.rows
    ]
    return UserListResponse(
        users=users,
        total=page.total,
        has_more=page.has_more,
        offset=offset,
    )


@router.get("/users/{user_id}/profile", response_model=UserProfileSchema)
async def get_user_profile(
    db: Db,
    user_id: int,
    guild_id: int | None = Query(None, description="Scope stats to a guild"),
) -> UserProfileSchema:
    """Get detailed user profile with statistics."""
    async with db.session() as session:
        user = await archive_reads.user(session, user_id)
        if not user:
            raise_not_found("User not found")

        scope = Scope(guild=guild_id or None, author=user_id)
        summary = await archive_reads.summary(session, scope)
        top_channels = await archive_reads.channel_activity(session, scope, limit=10)
        monthly = await archive_reads.activity(
            session,
            scope,
            period=Period.MONTH,
            since=dt.datetime.now(dt.UTC) - ACTIVITY_WINDOW,
        )
        top_reactions = await archive_reads.reactions(session, scope, limit=10)

    return UserProfileSchema(
        id=user.id,
        username=user.username,
        discriminator=user.discriminator,
        global_name=user.global_name,
        avatar_url=user.avatar_url,
        bot=user.bot,
        display_name=user.global_name or user.username,
        total_messages=summary.messages,
        total_attachments=summary.attachments,
        total_reactions_received=summary.reactions,
        first_message_at=summary.first_message_at,
        last_message_at=summary.last_message_at,
        active_channels=summary.channels,
        avg_message_length=round(summary.average_length, 1),
        top_channels=[
            UserChannelActivity(
                channel_id=channel.channel_id,
                channel_name=channel.channel_name,
                message_count=channel.messages,
            )
            for channel in top_channels
        ],
        monthly_activity=[
            UserMonthlyActivity(
                period=bucket.start.strftime("%Y-%m"),
                label=bucket.start.strftime("%b %Y"),
                count=bucket.messages,
            )
            for bucket in monthly
        ],
        top_reactions_received=[
            {"emoji": reaction.emoji_name or "?", "count": reaction.count}
            for reaction in top_reactions
        ],
    )
