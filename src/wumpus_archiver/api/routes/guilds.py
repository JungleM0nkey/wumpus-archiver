"""Guild API route handlers."""

from fastapi import APIRouter

from wumpus_archiver.api.deps import Db
from wumpus_archiver.api.routes._helpers import raise_not_found
from wumpus_archiver.api.schemas import (
    ChannelSchema,
    GuildDetailSchema,
    GuildSchema,
)
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import Scope

router = APIRouter()


@router.get("/guilds", response_model=list[GuildSchema])
async def list_guilds(db: Db) -> list[GuildSchema]:
    """List all archived guilds."""
    async with db.session() as session:
        guilds = await archive_reads.guilds(session)
        counts = await archive_reads.guild_counts(session, [guild.id for guild in guilds])

        schemas = []
        for guild in guilds:
            schema = GuildSchema.model_validate(guild)
            schema.channel_count = counts[guild.id].channels
            schema.message_count = counts[guild.id].messages
            schemas.append(schema)

        return schemas


@router.get("/guilds/{guild_id}", response_model=GuildDetailSchema)
async def get_guild(db: Db, guild_id: int) -> GuildDetailSchema:
    """Get guild details with channels."""
    async with db.session() as session:
        guild = await archive_reads.guild(session, guild_id)
        if not guild:
            raise_not_found("Guild not found")

        channels = await archive_reads.guild_channels(session, guild_id)
        messages = await archive_reads.message_total(session, Scope(guild=guild_id))

        schema = GuildDetailSchema(
            **{k: v for k, v in guild.__dict__.items() if not k.startswith("_")}
        )
        schema.channels = [ChannelSchema.model_validate(ch) for ch in channels]
        schema.channel_count = len(channels)
        schema.message_count = messages

        return schema
