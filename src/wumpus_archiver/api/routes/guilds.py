"""Guild API route handlers."""

from fastapi import APIRouter, Request

from sqlalchemy import func, select

from wumpus_archiver.api.routes._helpers import get_db, raise_not_found
from wumpus_archiver.api.schemas import (
    ChannelSchema,
    GuildDetailSchema,
    GuildSchema,
)
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message

router = APIRouter()


@router.get("/guilds", response_model=list[GuildSchema])
async def list_guilds(request: Request) -> list[GuildSchema]:
    """List all archived guilds."""
    db = get_db(request)
    async with db.session() as session:
        result = await session.execute(select(Guild))
        guilds = result.scalars().all()

        schemas = []
        for guild in guilds:
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
    db = get_db(request)
    async with db.session() as session:
        result = await session.execute(
            select(Guild).where(Guild.id == guild_id)
        )
        guild = result.scalar_one_or_none()
        if not guild:
            raise_not_found("Guild not found")

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
