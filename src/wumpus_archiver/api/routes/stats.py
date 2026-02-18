"""Stats API route handlers."""

from fastapi import APIRouter, Path, Request
from sqlalchemy import func, select

from wumpus_archiver.api.routes._helpers import get_db, raise_not_found
from wumpus_archiver.api.schemas import StatsSchema
from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User

router = APIRouter()


@router.get("/guilds/{guild_id}/stats", response_model=StatsSchema)
async def get_guild_stats(request: Request, guild_id: int = Path(gt=0)) -> StatsSchema:
    """Get statistics for a guild."""
    db = get_db(request)
    async with db.session() as session:
        guild_result = await session.execute(select(Guild).where(Guild.id == guild_id))
        guild = guild_result.scalar_one_or_none()
        if not guild:
            raise_not_found("Guild not found")

        guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

        ch_count = await session.execute(
            select(func.count(Channel.id)).where(Channel.guild_id == guild_id)
        )

        msg_count = await session.execute(
            select(func.count(Message.id)).where(
                Message.channel_id.in_(guild_channels)
            )
        )

        user_count = await session.execute(
            select(func.count(func.distinct(Message.author_id))).where(
                Message.channel_id.in_(guild_channels)
            )
        )

        att_count = await session.execute(
            select(func.count(Attachment.id)).where(
                Attachment.message_id.in_(
                    select(Message.id).where(Message.channel_id.in_(guild_channels))
                )
            )
        )

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

        top_user_result = await session.execute(
            select(
                User.id,
                User.username,
                User.global_name,
                User.avatar_url,
                func.count(Message.id).label("count"),
            )
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
