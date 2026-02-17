"""MCP resource definitions for wumpus-archiver."""

import json

from fastmcp import FastMCP
from sqlalchemy import func, select

from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User


def register_resources(mcp: FastMCP) -> None:
    """Register all MCP resources on the server."""

    @mcp.resource("archive://guilds")
    async def list_guilds() -> str:
        """List all archived Discord guilds with channel and message counts."""
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            result = await session.execute(select(Guild))
            guilds = list(result.scalars().all())

            items = []
            for g in guilds:
                ch_count = (await session.execute(
                    select(func.count(Channel.id)).where(Channel.guild_id == g.id)
                )).scalar() or 0

                guild_channels = select(Channel.id).where(Channel.guild_id == g.id)
                msg_count = (await session.execute(
                    select(func.count(Message.id)).where(
                        Message.channel_id.in_(guild_channels)
                    )
                )).scalar() or 0

                items.append({
                    "id": str(g.id),
                    "name": g.name,
                    "icon_url": g.icon_url,
                    "channels": ch_count,
                    "messages": msg_count,
                    "last_scraped": g.last_scraped_at.isoformat() if g.last_scraped_at else None,
                    "scrape_count": g.scrape_count,
                })

            return json.dumps({"guilds": items, "total": len(items)})

    @mcp.resource("archive://guilds/{guild_id}")
    async def get_guild_detail(guild_id: int) -> str:
        """Get detailed information about a specific guild including all channels."""
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            guild_r = await session.execute(select(Guild).where(Guild.id == guild_id))
            guild = guild_r.scalar_one_or_none()
            if not guild:
                return json.dumps({"error": f"Guild {guild_id} not found"})

            ch_r = await session.execute(
                select(Channel)
                .where(Channel.guild_id == guild_id)
                .order_by(Channel.position)
            )
            channels = list(ch_r.scalars().all())

            return json.dumps({
                "id": str(guild.id),
                "name": guild.name,
                "icon_url": guild.icon_url,
                "member_count": guild.member_count,
                "last_scraped": guild.last_scraped_at.isoformat() if guild.last_scraped_at else None,
                "scrape_count": guild.scrape_count,
                "channels": [
                    {
                        "id": str(ch.id),
                        "name": ch.name,
                        "type": ch.type,
                        "topic": ch.topic,
                        "position": ch.position,
                        "message_count": ch.message_count,
                    }
                    for ch in channels
                ],
            })

    @mcp.resource("archive://guilds/{guild_id}/channels")
    async def list_guild_channels(guild_id: int) -> str:
        """List all channels in a guild sorted by position."""
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            result = await session.execute(
                select(Channel)
                .where(Channel.guild_id == guild_id)
                .order_by(Channel.position)
            )
            channels = list(result.scalars().all())

            return json.dumps({
                "guild_id": str(guild_id),
                "channels": [
                    {
                        "id": str(ch.id),
                        "name": ch.name,
                        "type": ch.type,
                        "topic": ch.topic,
                        "position": ch.position,
                        "message_count": ch.message_count,
                        "last_scraped": ch.last_scraped_at.isoformat() if ch.last_scraped_at else None,
                    }
                    for ch in channels
                ],
                "total": len(channels),
            })

    @mcp.resource("archive://channels/{channel_id}/recent")
    async def get_recent_messages(channel_id: int) -> str:
        """Get the 50 most recent messages in a channel."""
        from sqlalchemy.orm import selectinload

        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            # Get channel info
            ch_r = await session.execute(select(Channel).where(Channel.id == channel_id))
            channel = ch_r.scalar_one_or_none()
            ch_name = channel.name if channel else "unknown"

            result = await session.execute(
                select(Message)
                .where(Message.channel_id == channel_id)
                .options(selectinload(Message.author))
                .order_by(Message.created_at.desc())
                .limit(50)
            )
            messages = list(reversed(result.scalars().all()))

            return json.dumps({
                "channel_id": str(channel_id),
                "channel_name": ch_name,
                "messages": [
                    {
                        "id": str(m.id),
                        "author": m.author.display_name if m.author else "Unknown",
                        "content": m.content[:500],
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in messages
                ],
                "count": len(messages),
            })

    @mcp.resource("archive://guilds/{guild_id}/stats")
    async def get_guild_stats_resource(guild_id: int) -> str:
        """Guild statistics summary including totals and top contributors."""
        from wumpus_archiver.mcp.server import get_db
        from wumpus_archiver.models.attachment import Attachment

        db = get_db()
        async with db.session() as session:
            guild_r = await session.execute(select(Guild).where(Guild.id == guild_id))
            guild = guild_r.scalar_one_or_none()
            if not guild:
                return json.dumps({"error": f"Guild {guild_id} not found"})

            guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

            ch_count = (await session.execute(
                select(func.count(Channel.id)).where(Channel.guild_id == guild_id)
            )).scalar() or 0

            msg_count = (await session.execute(
                select(func.count(Message.id)).where(
                    Message.channel_id.in_(guild_channels)
                )
            )).scalar() or 0

            user_count = (await session.execute(
                select(func.count(func.distinct(Message.author_id))).where(
                    Message.channel_id.in_(guild_channels)
                )
            )).scalar() or 0

            att_count = (await session.execute(
                select(func.count(Attachment.id)).where(
                    Attachment.message_id.in_(
                        select(Message.id).where(Message.channel_id.in_(guild_channels))
                    )
                )
            )).scalar() or 0

            return json.dumps({
                "guild_name": guild.name,
                "total_channels": ch_count,
                "total_messages": msg_count,
                "total_users": user_count,
                "total_attachments": att_count,
            })

    @mcp.resource("archive://guilds/{guild_id}/users")
    async def list_guild_users(guild_id: int) -> str:
        """List the top 50 users in a guild by message count."""
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)

            result = await session.execute(
                select(
                    User.id,
                    User.username,
                    User.global_name,
                    func.count(Message.id).label("msg_count"),
                )
                .join(Message, Message.author_id == User.id)
                .where(Message.channel_id.in_(guild_channels))
                .group_by(User.id, User.username, User.global_name)
                .order_by(func.count(Message.id).desc())
                .limit(50)
            )

            users = [
                {
                    "id": str(uid),
                    "username": username,
                    "display_name": global_name or username,
                    "message_count": cnt,
                }
                for uid, username, global_name, cnt in result.all()
            ]

            return json.dumps({
                "guild_id": str(guild_id),
                "users": users,
                "total": len(users),
            })

    @mcp.resource("archive://users/{user_id}/profile")
    async def get_user_profile_resource(user_id: int) -> str:
        """User profile with message statistics and activity summary."""
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            user_r = await session.execute(select(User).where(User.id == user_id))
            user = user_r.scalar_one_or_none()
            if not user:
                return json.dumps({"error": f"User {user_id} not found"})

            total_msgs = (await session.execute(
                select(func.count(Message.id)).where(Message.author_id == user_id)
            )).scalar() or 0

            time_r = (await session.execute(
                select(func.min(Message.created_at), func.max(Message.created_at))
                .where(Message.author_id == user_id)
            )).one()
            first_at, last_at = time_r

            top_ch_r = await session.execute(
                select(Channel.name, func.count(Message.id).label("cnt"))
                .join(Message, Message.channel_id == Channel.id)
                .where(Message.author_id == user_id)
                .group_by(Channel.id, Channel.name)
                .order_by(func.count(Message.id).desc())
                .limit(5)
            )

            return json.dumps({
                "id": str(user.id),
                "username": user.username,
                "display_name": user.global_name or user.username,
                "bot": user.bot,
                "total_messages": total_msgs,
                "first_message": first_at.isoformat() if first_at else None,
                "last_message": last_at.isoformat() if last_at else None,
                "top_channels": [
                    {"channel": name, "messages": cnt}
                    for name, cnt in top_ch_r.all()
                ],
            })

    @mcp.resource("archive://scrape/history")
    async def get_scrape_history() -> str:
        """Recent scrape job history (last 50 jobs)."""
        from wumpus_archiver.api.scrape_manager import ScrapeJobManager
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        manager = ScrapeJobManager(db)
        jobs = manager.history

        return json.dumps({
            "jobs": [
                {
                    "id": j.id,
                    "guild_id": j.guild_id,
                    "status": j.status.value,
                    "channels_done": j.progress.channels_done,
                    "messages_scraped": j.progress.messages_scraped,
                    "started_at": j.started_at.isoformat() if j.started_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                }
                for j in jobs
            ],
            "total": len(jobs),
        })

    @mcp.resource("archive://downloads/stats")
    async def get_download_stats() -> str:
        """Attachment download statistics."""
        from wumpus_archiver.mcp.server import get_attachments_path, get_db
        from wumpus_archiver.models.attachment import Attachment

        db = get_db()
        async with db.session() as session:
            total = (await session.execute(
                select(func.count(Attachment.id))
            )).scalar() or 0

            downloaded = (await session.execute(
                select(func.count(Attachment.id)).where(
                    Attachment.download_status == "downloaded"
                )
            )).scalar() or 0

            pending = (await session.execute(
                select(func.count(Attachment.id)).where(
                    Attachment.download_status.is_(None)
                )
            )).scalar() or 0

            failed = (await session.execute(
                select(func.count(Attachment.id)).where(
                    Attachment.download_status == "failed"
                )
            )).scalar() or 0

            att_path = get_attachments_path()

            return json.dumps({
                "total_attachments": total,
                "downloaded": downloaded,
                "pending": pending,
                "failed": failed,
                "attachments_dir": str(att_path) if att_path else None,
            })
