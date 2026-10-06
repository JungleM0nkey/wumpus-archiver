"""Channel API route handlers."""

from fastapi import APIRouter

from sqlalchemy import select

from wumpus_archiver.api.deps import Db
from wumpus_archiver.api.schemas import ChannelListResponse, ChannelSchema
from wumpus_archiver.models.channel import Channel

router = APIRouter()


@router.get("/guilds/{guild_id}/channels", response_model=ChannelListResponse)
async def list_channels(db: Db, guild_id: int) -> ChannelListResponse:
    """List channels for a guild."""
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
