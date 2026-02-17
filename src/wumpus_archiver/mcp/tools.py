"""MCP tool definitions for wumpus-archiver."""

import json
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User


def register_tools(mcp: FastMCP) -> None:
    """Register all MCP tools on the server."""

    @mcp.tool
    async def search_messages(
        query: Annotated[str, "Search text to find in message content"],
        guild_id: Annotated[int | None, "Filter results to a specific guild"] = None,
        channel_id: Annotated[int | None, "Filter results to a specific channel"] = None,
        author_id: Annotated[int | None, "Filter results to a specific user"] = None,
        limit: Annotated[int, Field(description="Max results to return", ge=1, le=100)] = 25,
    ) -> str:
        """Search archived Discord messages by content.

        Returns matching messages with author, channel, and timestamp context.
        Use this to find specific conversations or topics in the archive.
        """
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            stmt = (
                select(Message)
                .options(selectinload(Message.author))
                .where(Message.content.ilike(f"%{query}%"))
                .order_by(Message.created_at.desc())
                .limit(limit)
            )
            if channel_id:
                stmt = stmt.where(Message.channel_id == channel_id)
            elif guild_id:
                stmt = stmt.where(
                    Message.channel_id.in_(
                        select(Channel.id).where(Channel.guild_id == guild_id)
                    )
                )
            if author_id:
                stmt = stmt.where(Message.author_id == author_id)

            result = await session.execute(stmt)
            messages = list(result.scalars().all())

            # Get channel names
            ch_ids = {m.channel_id for m in messages}
            ch_result = await session.execute(
                select(Channel.id, Channel.name).where(Channel.id.in_(ch_ids))
            )
            ch_map: dict[int, str] = dict(ch_result.all())  # type: ignore[arg-type]

            # Count total matches
            count_stmt = select(func.count(Message.id)).where(
                Message.content.ilike(f"%{query}%")
            )
            if channel_id:
                count_stmt = count_stmt.where(Message.channel_id == channel_id)
            elif guild_id:
                count_stmt = count_stmt.where(
                    Message.channel_id.in_(
                        select(Channel.id).where(Channel.guild_id == guild_id)
                    )
                )
            total = (await session.execute(count_stmt)).scalar() or 0

            items = []
            for msg in messages:
                author_name = msg.author.display_name if msg.author else "Unknown"
                items.append({
                    "id": str(msg.id),
                    "channel": ch_map.get(msg.channel_id, "unknown"),
                    "author": author_name,
                    "content": msg.content[:500],
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                })

            return json.dumps({
                "query": query,
                "total_matches": total,
                "returned": len(items),
                "results": items,
            })

    @mcp.tool
    async def browse_messages(
        channel_id: Annotated[int, "Discord channel ID to browse"],
        before: Annotated[int | None, "Get messages before this message ID"] = None,
        after: Annotated[int | None, "Get messages after this message ID"] = None,
        limit: Annotated[int, Field(description="Number of messages", ge=1, le=100)] = 50,
    ) -> str:
        """Browse messages in a specific channel with cursor-based pagination.

        Returns messages in chronological order with author and attachment info.
        Use before/after message IDs for pagination.
        """
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            stmt = (
                select(Message)
                .where(Message.channel_id == channel_id)
                .options(
                    selectinload(Message.author),
                    selectinload(Message.attachments),
                    selectinload(Message.reactions),
                )
                .order_by(Message.created_at.asc())
                .limit(limit + 1)
            )
            if before:
                stmt = stmt.where(Message.id < before)
            if after:
                stmt = stmt.where(Message.id > after)

            result = await session.execute(stmt)
            messages = list(result.scalars().all())

            has_more = len(messages) > limit
            if has_more:
                messages = messages[:limit]

            total_r = await session.execute(
                select(func.count(Message.id)).where(Message.channel_id == channel_id)
            )
            total = total_r.scalar() or 0

            items = []
            for msg in messages:
                author_name = msg.author.display_name if msg.author else "Unknown"
                item: dict[str, object] = {
                    "id": str(msg.id),
                    "author": author_name,
                    "content": msg.content[:1000],
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                if msg.attachments:
                    item["attachments"] = [
                        {"filename": a.filename, "content_type": a.content_type, "url": a.url}
                        for a in msg.attachments
                    ]
                if msg.reactions:
                    item["reactions"] = [
                        {"emoji": r.emoji_name or "?", "count": r.count}
                        for r in msg.reactions
                    ]
                items.append(item)

            return json.dumps({
                "channel_id": str(channel_id),
                "total_in_channel": total,
                "returned": len(items),
                "has_more": has_more,
                "first_id": str(messages[0].id) if messages else None,
                "last_id": str(messages[-1].id) if messages else None,
                "messages": items,
            })

    @mcp.tool
    async def get_guild_stats(
        guild_id: Annotated[int, "Discord guild ID to get statistics for"],
    ) -> str:
        """Get comprehensive statistics for an archived Discord guild.

        Returns channel count, message count, user count, top channels, and top users.
        """
        from wumpus_archiver.mcp.server import get_db

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

            top_ch_r = await session.execute(
                select(Channel.name, Channel.message_count)
                .where(Channel.guild_id == guild_id)
                .order_by(Channel.message_count.desc())
                .limit(10)
            )
            top_channels = [
                {"name": name, "message_count": count}
                for name, count in top_ch_r.all()
            ]

            top_user_r = await session.execute(
                select(User.username, User.global_name, func.count(Message.id).label("cnt"))
                .join(Message, Message.author_id == User.id)
                .where(Message.channel_id.in_(guild_channels))
                .group_by(User.id, User.username, User.global_name)
                .order_by(func.count(Message.id).desc())
                .limit(10)
            )
            top_users = [
                {"name": global_name or username, "message_count": cnt}
                for username, global_name, cnt in top_user_r.all()
            ]

            return json.dumps({
                "guild_name": guild.name,
                "total_channels": ch_count,
                "total_messages": msg_count,
                "total_users": user_count,
                "total_attachments": att_count,
                "top_channels": top_channels,
                "top_users": top_users,
            })

    @mcp.tool
    async def get_user_profile(
        user_id: Annotated[int, "Discord user ID to look up"],
        guild_id: Annotated[int | None, "Scope stats to a specific guild"] = None,
    ) -> str:
        """Get a detailed activity profile for a Discord user.

        Returns message counts, top channels, monthly activity, and reaction stats.
        """
        import datetime as dt

        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            user_r = await session.execute(select(User).where(User.id == user_id))
            user = user_r.scalar_one_or_none()
            if not user:
                return json.dumps({"error": f"User {user_id} not found"})

            if guild_id:
                guild_channels = select(Channel.id).where(Channel.guild_id == guild_id)
                msg_scope = Message.channel_id.in_(guild_channels)
            else:
                msg_scope = True  # type: ignore[assignment]

            user_msgs = select(Message).where(
                Message.author_id == user_id, msg_scope
            ).subquery()

            total_msgs = (await session.execute(
                select(func.count()).select_from(user_msgs)
            )).scalar() or 0

            total_att = (await session.execute(
                select(func.count(Attachment.id)).where(
                    Attachment.message_id.in_(select(user_msgs.c.id))
                )
            )).scalar() or 0

            total_reactions = (await session.execute(
                select(func.coalesce(func.sum(Reaction.count), 0)).where(
                    Reaction.message_id.in_(select(user_msgs.c.id))
                )
            )).scalar() or 0

            time_r = (await session.execute(
                select(func.min(user_msgs.c.created_at), func.max(user_msgs.c.created_at))
            )).one()
            first_msg_at, last_msg_at = time_r

            top_ch_r = await session.execute(
                select(Channel.name, func.count(Message.id).label("cnt"))
                .join(Message, Message.channel_id == Channel.id)
                .where(Message.author_id == user_id, msg_scope)
                .group_by(Channel.id, Channel.name)
                .order_by(func.count(Message.id).desc())
                .limit(5)
            )
            top_channels = [
                {"channel": name, "messages": cnt} for name, cnt in top_ch_r.all()
            ]

            cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=365)
            monthly_r = await session.execute(
                select(
                    func.strftime("%Y-%m", Message.created_at).label("period"),
                    func.count(Message.id).label("cnt"),
                )
                .where(Message.author_id == user_id, msg_scope, Message.created_at >= cutoff)
                .group_by("period")
                .order_by("period")
            )
            monthly = [
                {"period": p, "messages": c} for p, c in monthly_r.all()
            ]

            return json.dumps({
                "user": {
                    "id": str(user.id),
                    "username": user.username,
                    "display_name": user.global_name or user.username,
                    "bot": user.bot,
                },
                "total_messages": total_msgs,
                "total_attachments": total_att,
                "total_reactions_received": int(total_reactions),
                "first_message": first_msg_at.isoformat() if first_msg_at else None,
                "last_message": last_msg_at.isoformat() if last_msg_at else None,
                "top_channels": top_channels,
                "monthly_activity": monthly,
            })

    @mcp.tool
    async def start_scrape(
        guild_id: Annotated[int, "Discord guild ID to scrape"],
        channel_ids: Annotated[
            list[int] | None, "Specific channel IDs to scrape (omit for full guild)"
        ] = None,
    ) -> str:
        """Start a background scrape job to archive a Discord guild.

        Requires a Discord bot token to be configured.
        Only one scrape can run at a time.
        """
        from wumpus_archiver.api.scrape_manager import ScrapeJobManager
        from wumpus_archiver.mcp.server import get_db, get_discord_token

        token = get_discord_token()
        if not token:
            return json.dumps({
                "error": "No Discord bot token configured. "
                "Set DISCORD_BOT_TOKEN in environment."
            })

        db = get_db()
        manager = ScrapeJobManager(db)

        try:
            job = manager.start_scrape(guild_id, token, channel_ids)
            return json.dumps({
                "status": "started",
                "job_id": job.id,
                "guild_id": guild_id,
                "scope": "channels" if channel_ids else "guild",
                "channel_count": len(channel_ids) if channel_ids else None,
            })
        except RuntimeError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool
    async def cancel_scrape() -> str:
        """Cancel the currently running scrape job."""
        from wumpus_archiver.api.scrape_manager import ScrapeJobManager
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        manager = ScrapeJobManager(db)

        if manager.cancel():
            return json.dumps({"status": "cancelled"})
        return json.dumps({"status": "no_active_job", "message": "No scrape job is running"})

    @mcp.tool
    async def get_scrape_status() -> str:
        """Check the status of the current or most recent scrape job."""
        from wumpus_archiver.api.scrape_manager import ScrapeJobManager
        from wumpus_archiver.mcp.server import get_db, get_discord_token

        db = get_db()
        manager = ScrapeJobManager(db)

        job = manager.current_job
        if job:
            return json.dumps({
                "busy": manager.is_busy,
                "job": {
                    "id": job.id,
                    "guild_id": job.guild_id,
                    "status": job.status.value,
                    "channels_done": job.progress.channels_done,
                    "messages_scraped": job.progress.messages_scraped,
                    "attachments_found": job.progress.attachments_found,
                    "current_channel": job.progress.current_channel,
                    "errors": job.progress.errors[:5],
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                },
                "has_token": get_discord_token() is not None,
            })

        return json.dumps({
            "busy": False,
            "job": None,
            "has_token": get_discord_token() is not None,
            "recent_jobs": len(manager.history),
        })

    @mcp.tool
    async def download_attachments(
        guild_id: Annotated[int | None, "Guild to download images for (omit for all)"] = None,
    ) -> str:
        """Start downloading image attachments from the archive to local storage.

        Downloads run in the background. Check download stats to monitor progress.
        """
        import asyncio

        from wumpus_archiver.mcp.server import get_attachments_path, get_db
        from wumpus_archiver.utils.downloader import ImageDownloader

        db = get_db()
        att_path = get_attachments_path()
        if not att_path:
            return json.dumps({
                "error": "No attachments directory configured. "
                "Use --attachments-dir when starting the MCP server."
            })

        att_path.mkdir(parents=True, exist_ok=True)
        downloader = ImageDownloader(database=db, output_dir=att_path, concurrency=5)

        async def _run() -> dict[str, object]:
            if guild_id:
                stats = await downloader.download_guild_images(guild_id)
            else:
                stats = await downloader.download_all_images()
            return {
                "total": stats.total,
                "downloaded": stats.downloaded,
                "already_exists": stats.already_exists,
                "skipped": stats.skipped,
                "failed": stats.failed,
                "total_mb": round(stats.total_bytes / 1024 / 1024, 1),
            }

        # Run download as a background task
        asyncio.create_task(_run())
        return json.dumps({
            "status": "download_started",
            "guild_id": guild_id,
            "output_dir": str(att_path),
        })
