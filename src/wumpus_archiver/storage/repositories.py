"""Repository pattern implementations."""

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User


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

    async def get_by_guild(self, guild_id: int) -> list[Channel]:
        """Get all channels for a guild."""
        result = await self.session.execute(select(Channel).where(Channel.guild_id == guild_id))
        return list(result.scalars().all())

    async def upsert(self, channel: Channel) -> Channel:
        """Insert or update channel."""
        existing = await self.get_by_id(channel.id)
        if existing:
            existing.name = channel.name
            existing.topic = channel.topic
            existing.position = channel.position
            existing.parent_id = channel.parent_id
            return existing
        else:
            self.session.add(channel)
            return channel

    async def update_message_metadata(
        self, channel_id: int, last_message_id: int, increment: int = 1
    ) -> None:
        """Update channel message count and last message."""
        channel = await self.get_by_id(channel_id)
        if channel:
            channel.last_message_id = last_message_id
            channel.message_count += increment
            channel.last_scraped_at = datetime.now(UTC)


class MessageRepository:
    """Repository for Message operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, message_id: int) -> Message | None:
        """Get message by ID."""
        result = await self.session.execute(select(Message).where(Message.id == message_id))
        return result.scalar_one_or_none()

    async def get_by_channel(
        self,
        channel_id: int,
        before_id: int | None = None,
        after_id: int | None = None,
        limit: int = 100,
    ) -> list[Message]:
        """Get messages from a channel with pagination."""
        query = (
            select(Message)
            .where(Message.channel_id == channel_id)
            .order_by(desc(Message.created_at))
            .limit(limit)
        )

        if before_id:
            query = query.where(Message.id < before_id)
        if after_id:
            query = query.where(Message.id > after_id)

        result = await self.session.execute(query)
        return list(result.scalars().all())

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
