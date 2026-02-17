"""Discord bot scraper implementation."""

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import discord
from discord.ext import commands
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database
from wumpus_archiver.storage.repositories import (
    AttachmentRepository,
    ChannelRepository,
    GuildRepository,
    MessageRepository,
    ReactionRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


class ArchiverBot:
    """Discord bot for archiving server data."""

    def __init__(self, token: str, database: Database) -> None:
        """Initialize the archiver bot.

        Args:
            token: Discord bot token
            database: Database instance for storage
        """
        self.token = token
        self.database = database
        self._ready_event = asyncio.Event()
        self._bot_task: asyncio.Task[None] | None = None

        # Setup Discord intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        self.client = commands.Bot(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

        # Register event handlers
        self.client.event(self.on_ready)

    async def on_ready(self) -> None:
        """Called when bot is ready."""
        if self.client.user:
            logger.info("Logged in as %s (ID: %s)", self.client.user, self.client.user.id)
        self._ready_event.set()

    async def scrape_guild(
        self,
        guild_id: int,
        progress_callback: Callable[[str, int], None] | None = None,
        channel_done_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, object]:
        """Scrape all data from a guild.

        Args:
            guild_id: Discord guild ID
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with scraping statistics
        """
        guild = self.client.get_guild(guild_id)
        if not guild:
            raise ValueError(f"Guild {guild_id} not found or bot is not a member")

        # --- Permission & visibility diagnostics ---
        self._log_channel_diagnostics(guild)

        stats: dict[str, object] = {
            "guild_name": guild.name,
            "channels_scraped": 0,
            "messages_scraped": 0,
            "attachments_found": 0,
            "errors": [],
        }
        channels_scraped = 0
        messages_scraped = 0
        attachments_found = 0
        errors: list[str] = []

        async with self.database.session() as session:
            # Save guild info
            await self._save_guild(session, guild)

            # Collect all scrapeable channels: text, voice, and stage channels
            scrapeable_channels: list[
                discord.TextChannel | discord.VoiceChannel | discord.StageChannel
            ] = []
            scrapeable_channels.extend(guild.text_channels)
            scrapeable_channels.extend(guild.voice_channels)
            scrapeable_channels.extend(guild.stage_channels)

            # Also include forum channels if available
            for forum in getattr(guild, "forum_channels", []):
                scrapeable_channels.append(forum)

            # Scrape each channel
            for channel in scrapeable_channels:
                try:
                    channel_stats = await self._scrape_channel(
                        session, channel, progress_callback
                    )
                    channels_scraped += 1
                    messages_scraped += channel_stats["messages"]
                    attachments_found += channel_stats["attachments"]
                    if channel_done_callback:
                        channel_done_callback(
                            channel_stats["messages"], channel_stats["attachments"]
                        )
                except discord.Forbidden:
                    error_msg = f"No permission to scrape #{channel.name}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
                except Exception as e:
                    error_msg = f"Error scraping channel {channel.name}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Scrape active threads
            for thread in guild.threads:
                try:
                    channel_stats = await self._scrape_channel(session, thread, progress_callback)
                    channels_scraped += 1
                    messages_scraped += channel_stats["messages"]
                    attachments_found += channel_stats["attachments"]
                    if channel_done_callback:
                        channel_done_callback(
                            channel_stats["messages"], channel_stats["attachments"]
                        )
                except Exception as e:
                    error_msg = f"Error scraping thread {thread.name}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Scrape archived threads (public)
            try:
                for text_channel in guild.text_channels:
                    async for thread in text_channel.archived_threads(limit=None):
                        try:
                            channel_stats = await self._scrape_channel(
                                session, thread, progress_callback
                            )
                            channels_scraped += 1
                            messages_scraped += channel_stats["messages"]
                            attachments_found += channel_stats["attachments"]
                            if channel_done_callback:
                                channel_done_callback(
                                    channel_stats["messages"],
                                    channel_stats["attachments"],
                                )
                        except Exception as e:
                            error_msg = f"Error scraping archived thread {thread.name}: {e}"
                            errors.append(error_msg)
                            logger.error(error_msg)
            except discord.Forbidden:
                errors.append("No permission to list archived threads")

            # Update guild scrape metadata
            guild_repo = GuildRepository(session)
            await guild_repo.update_scrape_metadata(guild_id)

        stats["channels_scraped"] = channels_scraped
        stats["messages_scraped"] = messages_scraped
        stats["attachments_found"] = attachments_found
        stats["errors"] = errors

        return stats

    async def scrape_channels(
        self,
        guild_id: int,
        channel_ids: list[int],
        progress_callback: Callable[[str, int], None] | None = None,
        channel_done_callback: Callable[[int, int], None] | None = None,
    ) -> dict[str, object]:
        """Scrape specific channels from a guild.

        Args:
            guild_id: Discord guild ID
            channel_ids: List of channel IDs to scrape
            progress_callback: Optional callback for progress updates
            channel_done_callback: Optional callback when a channel finishes

        Returns:
            Dict with scraping statistics
        """
        guild = self.client.get_guild(guild_id)
        if not guild:
            raise ValueError(f"Guild {guild_id} not found or bot is not a member")

        stats: dict[str, object] = {
            "guild_name": guild.name,
            "channels_scraped": 0,
            "channels_total": len(channel_ids),
            "messages_scraped": 0,
            "attachments_found": 0,
            "errors": [],
        }
        channels_scraped = 0
        messages_scraped = 0
        attachments_found = 0
        errors: list[str] = []

        async with self.database.session() as session:
            # Save guild info
            await self._save_guild(session, guild)

            for channel_id in channel_ids:
                # Try to find the channel in the guild
                channel = guild.get_channel(channel_id)
                if channel is None:
                    # Check if it's a thread
                    channel = guild.get_thread(channel_id)

                if channel is None:
                    errors.append(f"Channel {channel_id} not found in guild")
                    continue

                if not isinstance(
                    channel,
                    (
                        discord.TextChannel,
                        discord.VoiceChannel,
                        discord.StageChannel,
                        discord.ForumChannel,
                        discord.Thread,
                    ),
                ):
                    errors.append(
                        f"Channel #{channel.name} ({channel_id}) is not a scrapeable type"
                    )
                    continue

                try:
                    channel_stats = await self._scrape_channel(
                        session, channel, progress_callback
                    )
                    channels_scraped += 1
                    messages_scraped += channel_stats["messages"]
                    attachments_found += channel_stats["attachments"]
                    if channel_done_callback:
                        channel_done_callback(
                            channel_stats["messages"], channel_stats["attachments"]
                        )
                except discord.Forbidden:
                    error_msg = f"No permission to scrape #{channel.name}"
                    errors.append(error_msg)
                    logger.warning(error_msg)
                except Exception as e:
                    error_msg = f"Error scraping channel {channel.name}: {e}"
                    errors.append(error_msg)
                    logger.error(error_msg)

            # Scrape threads inside selected text channels
            scraped_thread_ids: set[int] = set()
            for channel_id in channel_ids:
                ch = guild.get_channel(channel_id)
                if not isinstance(ch, discord.TextChannel):
                    continue

                # Active threads in the channel
                for thread in ch.threads:
                    if thread.id in scraped_thread_ids:
                        continue
                    scraped_thread_ids.add(thread.id)
                    try:
                        thread_stats = await self._scrape_channel(
                            session, thread, progress_callback
                        )
                        channels_scraped += 1
                        messages_scraped += thread_stats["messages"]
                        attachments_found += thread_stats["attachments"]
                        if channel_done_callback:
                            channel_done_callback(
                                thread_stats["messages"], thread_stats["attachments"]
                            )
                    except Exception as e:
                        errors.append(f"Error scraping thread {thread.name}: {e}")

                # Archived threads in the channel
                try:
                    async for thread in ch.archived_threads(limit=None):
                        if thread.id in scraped_thread_ids:
                            continue
                        scraped_thread_ids.add(thread.id)
                        try:
                            thread_stats = await self._scrape_channel(
                                session, thread, progress_callback
                            )
                            channels_scraped += 1
                            messages_scraped += thread_stats["messages"]
                            attachments_found += thread_stats["attachments"]
                            if channel_done_callback:
                                channel_done_callback(
                                    thread_stats["messages"],
                                    thread_stats["attachments"],
                                )
                        except Exception as e:
                            errors.append(
                                f"Error scraping archived thread {thread.name}: {e}"
                            )
                except discord.Forbidden:
                    errors.append(f"No permission to list archived threads in #{ch.name}")

            # Update guild scrape metadata
            guild_repo = GuildRepository(session)
            await guild_repo.update_scrape_metadata(guild_id)

        stats["channels_scraped"] = channels_scraped
        stats["messages_scraped"] = messages_scraped
        stats["attachments_found"] = attachments_found
        stats["errors"] = errors

        return stats

    def _log_channel_diagnostics(self, guild: discord.Guild) -> None:
        """Log channel visibility diagnostics and permission warnings.

        Checks whether the bot has Administrator permission (required to see
        all private channels) and reports per-channel permission issues.

        Args:
            guild: The Discord guild to diagnose.
        """
        bot_member = guild.me
        guild_perms = bot_member.guild_permissions

        logger.info("=" * 60)
        logger.info("  Channel Diagnostics for: %s", guild.name)
        logger.info("=" * 60)

        # Check Administrator permission
        if guild_perms.administrator:
            logger.info("Bot has Administrator permission — all channels visible")
        else:
            logger.warning(
                "Bot does NOT have Administrator permission. "
                "Private channels where the bot's role lacks VIEW_CHANNEL "
                "will be completely invisible and silently skipped. "
                "Grant the bot Administrator to ensure full archival."
            )

        # Count visible channels by type
        text_count = len(guild.text_channels)
        voice_count = len(guild.voice_channels)
        stage_count = len(guild.stage_channels)
        forum_count = len(getattr(guild, "forum_channels", []))
        category_count = len(guild.categories)
        total_visible = text_count + voice_count + stage_count + forum_count

        logger.info("Visible channels: %d total", total_visible)
        logger.info(
            "  Text: %d, Voice: %d, Stage: %d, Forum: %d, Categories: %d",
            text_count, voice_count, stage_count, forum_count, category_count,
        )

        # Per-channel permission audit
        read_blocked: list[str] = []
        history_blocked: list[str] = []
        all_channels: list[
            discord.TextChannel
            | discord.VoiceChannel
            | discord.StageChannel
            | discord.ForumChannel
        ] = []
        all_channels.extend(guild.text_channels)
        all_channels.extend(guild.voice_channels)
        all_channels.extend(guild.stage_channels)
        for forum in getattr(guild, "forum_channels", []):
            all_channels.append(forum)

        for channel in all_channels:
            perms = channel.permissions_for(bot_member)
            if not perms.view_channel:
                # Shouldn't happen (channel wouldn't be in cache), but log it
                read_blocked.append(f"  #{channel.name} (id={channel.id})")
            elif not perms.read_message_history:
                history_blocked.append(f"  #{channel.name} (id={channel.id})")

        if history_blocked:
            logger.warning(
                "%d channel(s) visible but missing READ_MESSAGE_HISTORY:",
                len(history_blocked),
            )
            for ch_name in history_blocked:
                logger.warning(ch_name)

        if not guild_perms.administrator:
            logger.info(
                "To see private channels, either: "
                "1. Give the bot 'Administrator' permission, OR "
                "2. Add the bot's role to each private channel's permissions "
                "with VIEW_CHANNEL + READ_MESSAGE_HISTORY enabled."
            )

        logger.info("=" * 60)

    async def _save_guild(self, session: AsyncSession, guild: discord.Guild) -> Guild:
        """Save guild data to database."""
        guild_repo = GuildRepository(session)

        db_guild = Guild(
            id=guild.id,
            name=guild.name,
            icon_url=str(guild.icon.url) if guild.icon else None,
            owner_id=guild.owner_id,
            member_count=guild.member_count,
        )

        return await guild_repo.upsert(db_guild)

    async def _scrape_channel(
        self,
        session: AsyncSession,
        channel: discord.TextChannel | discord.VoiceChannel | discord.Thread | discord.StageChannel,
        progress_callback: Callable[[str, int], None] | None = None,
    ) -> dict[str, int]:
        """Scrape all messages from a channel or thread.

        Args:
            session: Database session
            channel: Discord channel, thread, or forum channel
            progress_callback: Optional progress callback

        Returns:
            Dict with channel scraping stats
        """
        channel_repo = ChannelRepository(session)

        # Resolve guild_id and parent_id for threads vs channels
        guild_id = channel.guild.id
        topic = getattr(channel, "topic", None)
        position = getattr(channel, "position", 0)
        parent_id = getattr(channel, "parent_id", None) or getattr(channel, "category_id", None)

        # Save channel info
        db_channel = Channel(
            id=channel.id,
            guild_id=guild_id,
            name=channel.name,
            type=channel.type.value,
            topic=topic,
            position=position,
            parent_id=parent_id,
        )
        await channel_repo.upsert(db_channel)
        await session.commit()

        stats = {"messages": 0, "attachments": 0}
        first_message_id: int | None = None
        last_message_id: int | None = None
        batch_size = 100

        # Report channel name immediately
        if progress_callback:
            progress_callback(channel.name, 0)

        # Check for existing archived messages to enable incremental scraping.
        # If we already have messages for this channel, only fetch newer ones.
        existing_channel = await channel_repo.get_by_id(channel.id)
        existing_last_id = existing_channel.last_message_id if existing_channel else None

        if existing_last_id:
            # Incremental: only fetch messages after the last archived one
            history_kwargs = {
                "limit": None,
                "after": discord.Object(id=existing_last_id),
                "oldest_first": True,
            }
            logger.info("Incremental scrape for #%s (after message %s)", channel.name, existing_last_id)
        else:
            # Full scrape: fetch everything
            history_kwargs = {"limit": None, "oldest_first": False}
            logger.info("Full scrape for #%s (no prior data)", channel.name)

        async for message in channel.history(**history_kwargs):
            try:
                await self._save_message(session, message)
                stats["messages"] += 1

                # Track oldest/newest message IDs (works regardless of iteration order)
                if first_message_id is None:
                    first_message_id = message.id
                    last_message_id = message.id
                else:
                    if message.id < first_message_id:
                        first_message_id = message.id
                    if message.id > last_message_id:
                        last_message_id = message.id

                if message.attachments:
                    stats["attachments"] += len(message.attachments)

                # Commit in batches to avoid long-running transactions
                if stats["messages"] % batch_size == 0:
                    await session.commit()

                    if progress_callback:
                        progress_callback(
                            channel.name,
                            stats["messages"],
                        )

            except Exception as e:
                # Rollback the failed transaction so subsequent saves aren't poisoned
                await session.rollback()
                logger.error("Error saving message %s: %s", message.id, e)

        # Final commit for remaining messages
        await session.commit()

        # Update channel metadata
        if stats["messages"] > 0:
            if first_message_id is not None:
                db_channel.first_message_id = first_message_id
            if last_message_id is not None:
                db_channel.last_message_id = last_message_id
                await channel_repo.update_message_metadata(
                    channel.id, last_message_id, stats["messages"]
                )
        else:
            # No new messages — still mark the channel as scraped so analyze
            # knows we checked it recently.
            await channel_repo.mark_scraped(channel.id)

        return stats

    async def _save_message(
        self,
        session: AsyncSession,
        message: discord.Message,
    ) -> Message:
        """Save a message and its related data."""
        # Save author first
        if message.author:
            await self._save_user(session, message.author)

        # Create message
        db_message = Message(
            id=message.id,
            channel_id=message.channel.id,
            author_id=message.author.id if message.author else None,
            content=message.content or "",
            clean_content=message.clean_content or "",
            created_at=message.created_at.astimezone(UTC),
            edited_at=(
                message.edited_at.astimezone(UTC)
                if message.edited_at
                else None
            ),
            pinned=message.pinned,
            tts=message.tts,
            mention_everyone=message.mention_everyone,
            embeds=(
                json.dumps([embed.to_dict() for embed in message.embeds])
                if message.embeds
                else None
            ),
            reference_id=message.reference.message_id if message.reference else None,
            scraped_at=datetime.now(UTC),
        )

        message_repo = MessageRepository(session)
        db_message = await message_repo.upsert(db_message)

        # Save attachments
        for attachment in message.attachments:
            await self._save_attachment(session, attachment, message.id)

        # Save reactions (flush first so reaction inserts don't poison the message)
        await session.flush()
        for reaction in message.reactions:
            try:
                await self._save_reaction(session, reaction, message.id)
                await session.flush()
            except Exception:
                await session.rollback()
                # Re-add the message to the session since rollback detaches it
                await session.merge(db_message)

        return db_message

    async def _save_user(
        self,
        session: AsyncSession,
        user: discord.User | discord.Member,
    ) -> User:
        """Save user data."""
        user_repo = UserRepository(session)

        avatar_url = str(user.avatar.url) if user.avatar else None

        db_user = User(
            id=user.id,
            username=user.name,
            discriminator=user.discriminator if hasattr(user, "discriminator") else None,
            global_name=user.global_name if hasattr(user, "global_name") else None,
            avatar_url=avatar_url,
            bot=user.bot,
        )

        return await user_repo.upsert(db_user)

    async def _save_attachment(
        self,
        session: AsyncSession,
        attachment: discord.Attachment,
        message_id: int,
    ) -> Attachment:
        """Save attachment data."""
        attachment_repo = AttachmentRepository(session)

        db_attachment = Attachment(
            id=attachment.id,
            message_id=message_id,
            filename=attachment.filename,
            content_type=attachment.content_type,
            size=attachment.size,
            url=attachment.url,
            proxy_url=attachment.proxy_url,
            width=attachment.width,
            height=attachment.height,
            download_status="pending",
        )

        return await attachment_repo.upsert(db_attachment)

    async def _save_reaction(
        self,
        session: AsyncSession,
        reaction: discord.Reaction,
        message_id: int,
    ) -> Reaction:
        """Save reaction data."""
        reaction_repo = ReactionRepository(session)

        emoji_name = reaction.emoji.name if hasattr(reaction.emoji, "name") else str(reaction.emoji)
        emoji_id = reaction.emoji.id if hasattr(reaction.emoji, "id") else None

        db_reaction = Reaction(
            message_id=message_id,
            emoji_name=emoji_name,
            emoji_id=emoji_id,
            emoji_animated=(
                reaction.emoji.animated if hasattr(reaction.emoji, "animated") else False
            ),
            count=reaction.count,
        )

        return await reaction_repo.upsert(db_reaction)

    async def start(self) -> None:
        """Start the bot and wait until it's ready."""
        self._bot_task = asyncio.create_task(self.client.start(self.token))
        await self._ready_event.wait()

    async def close(self) -> None:
        """Close the bot connection."""
        await self.client.close()
        if self._bot_task is not None:
            self._bot_task.cancel()
            try:
                await self._bot_task
            except asyncio.CancelledError:
                pass
