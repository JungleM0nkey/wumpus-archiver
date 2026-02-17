"""MCP prompt definitions for wumpus-archiver."""

import json

from fastmcp import FastMCP
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User


def register_prompts(mcp: FastMCP) -> None:
    """Register all MCP prompts on the server."""

    @mcp.prompt
    async def analyze_channel(
        channel_id: str,
        focus: str = "general",
    ) -> str:
        """Analyze conversation patterns and topics in a Discord channel.

        Args:
            channel_id: The Discord channel ID to analyze.
            focus: Analysis focus — general, sentiment, topics, or activity.
        """
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            ch_r = await session.execute(
                select(Channel).where(Channel.id == int(channel_id))
            )
            channel = ch_r.scalar_one_or_none()
            ch_name = channel.name if channel else "unknown"

            msg_count = (await session.execute(
                select(func.count(Message.id)).where(
                    Message.channel_id == int(channel_id)
                )
            )).scalar() or 0

            result = await session.execute(
                select(Message)
                .where(Message.channel_id == int(channel_id))
                .options(selectinload(Message.author))
                .order_by(Message.created_at.desc())
                .limit(100)
            )
            messages = list(reversed(result.scalars().all()))

            conversation = "\n".join(
                f"[{m.created_at.strftime('%Y-%m-%d %H:%M') if m.created_at else '?'}] "
                f"{m.author.display_name if m.author else 'Unknown'}: "
                f"{m.content[:300]}"
                for m in messages
            )

            return (
                f"Analyze the conversation in Discord channel #{ch_name} "
                f"(ID: {channel_id}, {msg_count} total messages).\n"
                f"Focus: {focus}\n\n"
                f"Here are the most recent {len(messages)} messages:\n\n"
                f"{conversation}\n\n"
                f"Please provide:\n"
                f"1. A summary of the main topics discussed\n"
                f"2. Key participants and their roles in the conversation\n"
                f"3. Notable patterns or trends\n"
                f"4. Any actionable insights"
            )

    @mcp.prompt
    async def summarize_user(
        user_id: str,
        guild_id: str = "",
    ) -> str:
        """Summarize a Discord user's activity and contributions.

        Args:
            user_id: The Discord user ID to summarize.
            guild_id: Optional guild ID to scope the summary.
        """
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            user_r = await session.execute(
                select(User).where(User.id == int(user_id))
            )
            user = user_r.scalar_one_or_none()
            if not user:
                return f"User {user_id} not found in the archive."

            display = user.global_name or user.username
            scope = Message.author_id == int(user_id)

            total_msgs = (await session.execute(
                select(func.count(Message.id)).where(scope)
            )).scalar() or 0

            top_ch_r = await session.execute(
                select(Channel.name, func.count(Message.id).label("cnt"))
                .join(Message, Message.channel_id == Channel.id)
                .where(scope)
                .group_by(Channel.id, Channel.name)
                .order_by(func.count(Message.id).desc())
                .limit(5)
            )
            top_channels = [f"#{name} ({cnt} msgs)" for name, cnt in top_ch_r.all()]

            recent_r = await session.execute(
                select(Message)
                .where(scope)
                .order_by(Message.created_at.desc())
                .limit(20)
            )
            recent = list(recent_r.scalars().all())
            recent_samples = "\n".join(
                f"- [{m.created_at.strftime('%Y-%m-%d') if m.created_at else '?'}] "
                f"{m.content[:200]}"
                for m in recent
            )

            return (
                f"Summarize the Discord activity of user **{display}** "
                f"(@{user.username}, ID: {user_id}).\n\n"
                f"Statistics:\n"
                f"- Total messages: {total_msgs}\n"
                f"- Bot account: {'Yes' if user.bot else 'No'}\n"
                f"- Most active in: {', '.join(top_channels) if top_channels else 'N/A'}\n\n"
                f"Recent messages (sample):\n{recent_samples}\n\n"
                f"Please provide:\n"
                f"1. A profile summary of this user\n"
                f"2. Their main interests/topics based on message content\n"
                f"3. Their engagement pattern (how active, when most active)\n"
                f"4. Their role in the community (helper, lurker, leader, etc.)"
            )

    @mcp.prompt
    async def search_and_analyze(
        query: str,
        guild_id: str = "",
    ) -> str:
        """Search for a topic in the archive and provide contextual analysis.

        Args:
            query: Search text to find in messages.
            guild_id: Optional guild ID to scope the search.
        """
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        async with db.session() as session:
            stmt = (
                select(Message)
                .options(selectinload(Message.author))
                .where(Message.content.ilike(f"%{query}%"))
                .order_by(Message.created_at.desc())
                .limit(50)
            )
            if guild_id:
                stmt = stmt.where(
                    Message.channel_id.in_(
                        select(Channel.id).where(Channel.guild_id == int(guild_id))
                    )
                )

            result = await session.execute(stmt)
            messages = list(result.scalars().all())

            ch_ids = {m.channel_id for m in messages}
            ch_r = await session.execute(
                select(Channel.id, Channel.name).where(Channel.id.in_(ch_ids))
            )
            ch_map: dict[int, str] = dict(ch_r.all())  # type: ignore[arg-type]

            total_r = await session.execute(
                select(func.count(Message.id)).where(
                    Message.content.ilike(f"%{query}%")
                )
            )
            total = total_r.scalar() or 0

            matches = "\n".join(
                f"- [{m.created_at.strftime('%Y-%m-%d %H:%M') if m.created_at else '?'}] "
                f"#{ch_map.get(m.channel_id, '?')} | "
                f"{m.author.display_name if m.author else 'Unknown'}: "
                f"{m.content[:300]}"
                for m in messages
            )

            return (
                f"Analyze discussions about **\"{query}\"** in the Discord archive.\n\n"
                f"Found {total} total matches. Here are the {len(messages)} most recent:\n\n"
                f"{matches}\n\n"
                f"Please provide:\n"
                f"1. A summary of how this topic was discussed\n"
                f"2. Key opinions or perspectives shared\n"
                f"3. Timeline of the discussion (when it peaked, evolved)\n"
                f"4. Any conclusions or resolutions reached"
            )

    @mcp.prompt
    async def scrape_report() -> str:
        """Generate a report on the most recent scrape operation."""
        from wumpus_archiver.api.scrape_manager import ScrapeJobManager
        from wumpus_archiver.mcp.server import get_db

        db = get_db()
        manager = ScrapeJobManager(db)
        jobs = manager.history

        if not jobs:
            return (
                "No scrape jobs have been run in this session. "
                "Use the start_scrape tool to begin archiving a Discord server."
            )

        last = jobs[0]
        job_info = json.dumps({
            "id": last.id,
            "guild_id": last.guild_id,
            "status": last.status.value,
            "channels_done": last.progress.channels_done,
            "messages_scraped": last.progress.messages_scraped,
            "attachments_found": last.progress.attachments_found,
            "errors": last.progress.errors[:10],
            "started_at": last.started_at.isoformat() if last.started_at else None,
            "completed_at": last.completed_at.isoformat() if last.completed_at else None,
            "error_message": last.error_message,
        }, indent=2)

        return (
            f"Generate a report for the most recent scrape operation.\n\n"
            f"Job data:\n```json\n{job_info}\n```\n\n"
            f"Total jobs in history: {len(jobs)}\n\n"
            f"Please provide:\n"
            f"1. A summary of what was scraped\n"
            f"2. Success/failure status with details\n"
            f"3. Any errors that occurred and potential fixes\n"
            f"4. Recommendations for next steps"
        )
