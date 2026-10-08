"""Repository pattern implementations."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.completed_scrape import CompletedScrape
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.archive_reads import GuildTotals


class GuildRepository:
    """Repository for Guild operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, guild_id: int) -> Guild | None:
        """Get guild by ID."""
        result = await self.session.execute(select(Guild).where(Guild.id == guild_id))
        return result.scalar_one_or_none()

    async def upsert(self, guild: Guild) -> Guild:
        """Insert or update guild."""
        existing = await self.get_by_id(guild.id)
        if existing:
            existing.name = guild.name
            existing.icon_url = guild.icon_url
            existing.owner_id = guild.owner_id
            existing.member_count = guild.member_count
            existing.updated_at = datetime.now(UTC)
            return existing
        else:
            self.session.add(guild)
            return guild

    async def update_scrape_metadata(self, guild_id: int) -> None:
        """Update guild scrape timestamps with atomic counter increment."""
        from sqlalchemy import update as sa_update

        guild = await self.get_by_id(guild_id)
        if guild:
            now = datetime.now(UTC)
            if not guild.first_scraped_at:
                guild.first_scraped_at = now
            guild.last_scraped_at = now

            # Atomic increment to avoid race conditions
            stmt = (
                sa_update(Guild)
                .where(Guild.id == guild_id)
                .values(scrape_count=Guild.scrape_count + 1)
            )
            await self.session.execute(stmt)


class ChannelRepository:
    """Repository for Channel operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, channel_id: int) -> Channel | None:
        """Get channel by ID."""
        result = await self.session.execute(select(Channel).where(Channel.id == channel_id))
        return result.scalar_one_or_none()

    async def upsert(self, channel: Channel) -> Channel:
        """Insert a channel, or refresh a stored one's details from Discord.

        Only what Discord says about the channel is copied: its name, type, topic,
        position and parent. The archive metadata (first and last message ids, message
        count, last scraped) is never taken from ``channel``, which a scraper builds
        fresh without it; ``update_message_metadata`` derives it from the archive.
        """
        existing = await self.get_by_id(channel.id)
        if existing:
            existing.name = channel.name
            existing.type = channel.type
            existing.topic = channel.topic
            existing.position = channel.position
            existing.parent_id = channel.parent_id
            return existing
        else:
            self.session.add(channel)
            return channel

    async def update_message_metadata(self, channel_id: int) -> None:
        """Record a finished scrape of a channel from the messages the archive holds for it.

        ``first_message_id`` and ``last_message_id`` name the channel's oldest and newest
        archived messages, in the readers' ``(created_at, id)`` order, and
        ``message_count`` counts them. All three are read from the archive rather than
        from what the scrape read, so a re-scrape cannot inflate the count (#69), a
        scrape that reaches older history moves the first id back (#70), and values an
        earlier scrape left wrong are corrected by the next one.
        """
        channel = await self.get_by_id(channel_id)
        if channel:
            in_channel = Message.channel_id == channel_id
            archived = await self.session.execute(
                select(func.count()).select_from(Message).where(in_channel)
            )
            channel.message_count = archived.scalar_one()
            oldest = await self.session.execute(
                select(Message.id)
                .where(in_channel)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .limit(1)
            )
            channel.first_message_id = oldest.scalar_one_or_none()
            newest = await self.session.execute(
                select(Message.id)
                .where(in_channel)
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(1)
            )
            channel.last_message_id = newest.scalar_one_or_none()
            channel.last_scraped_at = datetime.now(UTC)


class MessageRepository:
    """Repository for Message operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, message_id: int) -> Message | None:
        """Get message by ID."""
        result = await self.session.execute(select(Message).where(Message.id == message_id))
        return result.scalar_one_or_none()

    async def upsert(self, message: Message) -> Message:
        """Insert or update message."""
        existing = await self.get_by_id(message.id)
        if existing:
            # Update editable fields
            existing.content = message.content
            existing.clean_content = message.clean_content
            existing.edited_at = message.edited_at
            existing.embeds = message.embeds
            existing.pinned = message.pinned
            existing.updated_at = datetime.now(UTC)
            return existing
        else:
            self.session.add(message)
            return message

    async def bulk_upsert(self, messages: list[Message]) -> list[Message]:
        """Insert or update multiple messages efficiently."""
        result = []
        for message in messages:
            msg = await self.upsert(message)
            result.append(msg)
        return result


class UserRepository:
    """Repository for User operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: int) -> User | None:
        """Get user by ID."""
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def upsert(self, user: User) -> User:
        """Insert or update user."""
        existing = await self.get_by_id(user.id)
        if existing:
            existing.username = user.username
            existing.discriminator = user.discriminator
            existing.global_name = user.global_name
            existing.avatar_url = user.avatar_url
            existing.bot = user.bot
            return existing
        else:
            self.session.add(user)
            return user


class AttachmentRepository:
    """Repository for Attachment operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, attachment: Attachment) -> Attachment:
        """Insert or update attachment."""
        result = await self.session.execute(
            select(Attachment).where(Attachment.id == attachment.id)
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.local_path = attachment.local_path
            existing.download_status = attachment.download_status
            existing.content_hash = attachment.content_hash
            return existing
        else:
            self.session.add(attachment)
            return attachment


class ReactionRepository:
    """Repository for Reaction operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(self, reaction: Reaction) -> Reaction:
        """Insert or update reaction (by message + emoji)."""
        result = await self.session.execute(
            select(Reaction).where(
                Reaction.message_id == reaction.message_id,
                Reaction.emoji_name == reaction.emoji_name,
                Reaction.emoji_id == reaction.emoji_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.count = reaction.count
            return existing
        else:
            self.session.add(reaction)
            return reaction


class CompletedScrapeRepository:
    """Repository for the record each completed scrape job leaves (see ``docs/adr/0004``)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        guild_id: int,
        *,
        started_at: datetime,
        at_start: GuildTotals,
        completed_at: datetime | None = None,
    ) -> CompletedScrape:
        """Record that a scrape job of ``guild_id`` completed, with the totals it started from.

        ``at_start`` must be read before the job writes anything. Times are stored as
        naive UTC; ``completed_at`` defaults to now.
        """
        completed = completed_at or datetime.now(UTC)
        record = CompletedScrape(
            guild_id=guild_id,
            started_at=_naive_utc(started_at),
            completed_at=_naive_utc(completed),
            messages_at_start=at_start.messages,
            channels_at_start=at_start.channels,
            authors_at_start=at_start.authors,
            attachments_at_start=at_start.attachments,
        )
        self.session.add(record)
        return record


def _naive_utc(value: datetime) -> datetime:
    """The archive stores naive UTC; convert an aware datetime to that."""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
