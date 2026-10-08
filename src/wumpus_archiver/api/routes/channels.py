"""Channel API route handlers."""

from fastapi import APIRouter

from wumpus_archiver.api.deps import Db
from wumpus_archiver.api.schemas import ChannelListResponse, ChannelSchema
from wumpus_archiver.storage import archive_reads

router = APIRouter()


@router.get("/guilds/{guild_id}/channels", response_model=ChannelListResponse)
async def list_channels(db: Db, guild_id: int) -> ChannelListResponse:
    """List channels for a guild."""
    async with db.session() as session:
        channels = await archive_reads.guild_channels(session, guild_id)
        return ChannelListResponse(
            channels=[ChannelSchema.model_validate(ch) for ch in channels],
            total=len(channels),
        )
