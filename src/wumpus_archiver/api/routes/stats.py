"""Stats API route handlers."""

from fastapi import APIRouter

from wumpus_archiver.api.deps import Db
from wumpus_archiver.api.routes._helpers import raise_not_found
from wumpus_archiver.api.schemas import StatsSchema
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import AuthorSort, Scope

router = APIRouter()


@router.get("/guilds/{guild_id}/stats", response_model=StatsSchema)
async def get_guild_stats(db: Db, guild_id: int) -> StatsSchema:
    """Get statistics for a guild."""
    async with db.session() as session:
        guild = await archive_reads.guild(session, guild_id)
        if not guild:
            raise_not_found("Guild not found")

        scope = Scope(guild=guild_id)
        counts = await archive_reads.guild_counts(session, [guild_id])
        summary = await archive_reads.summary(session, scope)
        channels = await archive_reads.top_channels(session, guild_id, limit=10)
        authors = await archive_reads.authors(session, scope, sort=AuthorSort.MESSAGES, limit=10)

    return StatsSchema(
        guild_name=guild.name,
        total_channels=counts[guild_id].channels,
        total_messages=summary.messages,
        total_users=summary.authors,
        total_attachments=summary.attachments,
        top_channels=[
            {
                "id": str(channel.channel_id),
                "name": channel.name,
                "message_count": channel.message_count,
            }
            for channel in channels
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
    )
