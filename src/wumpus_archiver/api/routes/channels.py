"""Channel API route handlers."""

from fastapi import APIRouter

from wumpus_archiver.api.deps import Db
from wumpus_archiver.api.routes._helpers import raise_not_found
from wumpus_archiver.api.schemas import (
    ChannelActivityBucketSchema,
    ChannelActivitySchema,
    ChannelListResponse,
    ChannelSchema,
)
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.archive_reads import Period, Scope

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


@router.get("/channels/{channel_id}/activity", response_model=ChannelActivitySchema)
async def get_channel_activity(
    db: Db, channel_id: int, period: Period = Period.MONTH
) -> ChannelActivitySchema:
    """Messages per calendar month (or ISO week) in one channel, oldest first.

    The shape of the guild's activity, with each period's first message, which Browse's
    jump rail opens the reader at.
    """
    async with db.session() as session:
        if not await archive_reads.channel(session, channel_id):
            raise_not_found("Channel not found")
        buckets = await archive_reads.activity(
            session, Scope(channel=channel_id), period=period, with_first_message=True
        )

    return ChannelActivitySchema(
        period=period.value,
        buckets=[
            ChannelActivityBucketSchema(
                start=b.start, messages=b.messages, first_message_id=b.first_message_id
            )
            for b in buckets
            if b.first_message_id is not None
        ],
    )
