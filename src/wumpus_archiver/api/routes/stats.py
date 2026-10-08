"""Stats API route handlers."""

from fastapi import APIRouter

from wumpus_archiver.api.deps import Db
from wumpus_archiver.api.routes._helpers import raise_not_found
from wumpus_archiver.api.schemas import (
    ActivityBucketSchema,
    ActivitySchema,
    SinceLastScrapeSchema,
    StatsSchema,
)
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import AuthorSort, Period, Scope

router = APIRouter()


@router.get("/guilds/{guild_id}/stats", response_model=StatsSchema)
async def get_guild_stats(db: Db, guild_id: int) -> StatsSchema:
    """Get statistics for a guild, with their change since its last completed scrape job."""
    async with db.session() as session:
        guild = await archive_reads.guild(session, guild_id)
        if not guild:
            raise_not_found("Guild not found")

        scope = Scope(guild=guild_id)
        totals = await archive_reads.guild_totals(session, guild_id)
        top_channels = await archive_reads.top_channels(session, guild_id, limit=10)
        authors = await archive_reads.authors(session, scope, sort=AuthorSort.MESSAGES, limit=10)
        last_scrape = await archive_reads.last_completed_scrape(session, guild_id)

    since_last_scrape = None
    if last_scrape is not None:
        since_last_scrape = SinceLastScrapeSchema(
            started_at=last_scrape.started_at,
            completed_at=last_scrape.completed_at,
            messages=totals.messages - last_scrape.messages_at_start,
            channels=totals.channels - last_scrape.channels_at_start,
            authors=totals.authors - last_scrape.authors_at_start,
            attachments=totals.attachments - last_scrape.attachments_at_start,
        )

    return StatsSchema(
        guild_name=guild.name,
        total_channels=totals.channels,
        total_messages=totals.messages,
        total_users=totals.authors,
        total_attachments=totals.attachments,
        top_channels=[
            {
                "id": str(channel.channel_id),
                "name": channel.name,
                "message_count": channel.message_count,
            }
            for channel in top_channels
        ],
        top_users=[
            {
                "id": str(row.user.id),
                "username": row.user.username,
                "display_name": row.user.global_name or row.user.username,
                "avatar_url": row.user.avatar_url,
                "message_count": row.messages,
            }
            for row in authors.rows
        ],
        since_last_scrape=since_last_scrape,
    )


@router.get("/guilds/{guild_id}/activity", response_model=ActivitySchema)
async def get_guild_activity(
    db: Db, guild_id: int, period: Period = Period.MONTH
) -> ActivitySchema:
    """Messages per calendar month (or ISO week) over the whole guild, oldest first."""
    async with db.session() as session:
        if not await archive_reads.guild(session, guild_id):
            raise_not_found("Guild not found")
        buckets = await archive_reads.activity(session, Scope(guild=guild_id), period=period)

    return ActivitySchema(
        period=period.value,
        buckets=[ActivityBucketSchema(start=b.start, messages=b.messages) for b in buckets],
    )
