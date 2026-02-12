"""Tests for database models."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User


class TestGuildModel:
    """Tests for the Guild model."""

    async def test_create_guild(self, session: AsyncSession) -> None:
        """Test creating a guild."""
        guild = Guild(
            id=123456789,
            name="Test Guild",
            icon_url="https://example.com/icon.png",
            owner_id=987654321,
            member_count=100,
        )
        session.add(guild)
        await session.flush()

        result = await session.execute(select(Guild).where(Guild.id == 123456789))
        db_guild = result.scalar_one()
        assert db_guild.name == "Test Guild"
        assert db_guild.owner_id == 987654321
        assert db_guild.member_count == 100
        assert db_guild.scrape_count == 0

    async def test_guild_repr(self) -> None:
        """Test guild string representation."""
        guild = Guild(id=1, name="My Guild")
        assert "My Guild" in repr(guild)

    async def test_guild_defaults(self, session: AsyncSession) -> None:
        """Test guild default values."""
        guild = Guild(id=111, name="Default Guild")
        session.add(guild)
        await session.flush()

        result = await session.execute(select(Guild).where(Guild.id == 111))
        db_guild = result.scalar_one()
        assert db_guild.scrape_count == 0
        assert db_guild.first_scraped_at is None
        assert db_guild.last_scraped_at is None
        assert db_guild.icon_url is None


class TestChannelModel:
    """Tests for the Channel model."""

    async def test_create_channel(self, session: AsyncSession) -> None:
        """Test creating a channel with guild FK."""
        guild = Guild(id=100, name="Test Guild")
        session.add(guild)
        await session.flush()

        channel = Channel(
            id=200,
            guild_id=100,
            name="general",
            type=0,
            topic="General chat",
            position=1,
        )
        session.add(channel)
        await session.flush()

        result = await session.execute(select(Channel).where(Channel.id == 200))
        db_channel = result.scalar_one()
        assert db_channel.name == "general"
        assert db_channel.guild_id == 100
        assert db_channel.topic == "General chat"
        assert db_channel.message_count == 0

    async def test_channel_repr(self) -> None:
        """Test channel string representation."""
        channel = Channel(id=1, guild_id=1, name="general", type=0)
        assert "general" in repr(channel)


class TestUserModel:
    """Tests for the User model."""

    async def test_create_user(self, session: AsyncSession) -> None:
        """Test creating a user."""
        user = User(
            id=300,
            username="testuser",
            discriminator="1234",
            global_name="Test User",
            bot=False,
        )
        session.add(user)
        await session.flush()

        result = await session.execute(select(User).where(User.id == 300))
        db_user = result.scalar_one()
        assert db_user.username == "testuser"
        assert db_user.discriminator == "1234"
        assert db_user.bot is False

    async def test_user_display_name_global(self) -> None:
        """Test display_name prefers global_name."""
        user = User(id=1, username="bob", global_name="Bobby")
        assert user.display_name == "Bobby"

    async def test_user_display_name_fallback(self) -> None:
        """Test display_name falls back to username."""
        user = User(id=1, username="bob")
        assert user.display_name == "bob"


class TestMessageModel:
    """Tests for the Message model."""

    async def test_create_message(self, session: AsyncSession) -> None:
        """Test creating a message with all required fields."""
        guild = Guild(id=400, name="Test Guild")
        session.add(guild)
        await session.flush()

        channel = Channel(id=401, guild_id=400, name="general", type=0)
        session.add(channel)

        user = User(id=402, username="author", bot=False)
        session.add(user)
        await session.flush()

        now = datetime.now(UTC)
        message = Message(
            id=500,
            channel_id=401,
            author_id=402,
            content="Hello world!",
            clean_content="Hello world!",
            created_at=now,
            scraped_at=now,
        )
        session.add(message)
        await session.flush()

        result = await session.execute(select(Message).where(Message.id == 500))
        db_msg = result.scalar_one()
        assert db_msg.content == "Hello world!"
        assert db_msg.author_id == 402
        assert db_msg.pinned is False

    async def test_message_repr_short(self) -> None:
        """Test message repr with short content."""
        msg = Message(
            id=1,
            channel_id=1,
            content="Hi",
            clean_content="Hi",
            created_at=datetime.now(UTC),
            scraped_at=datetime.now(UTC),
        )
        assert "Hi" in repr(msg)

    async def test_message_repr_long(self) -> None:
        """Test message repr truncates long content."""
        msg = Message(
            id=1,
            channel_id=1,
            content="x" * 100,
            clean_content="x" * 100,
            created_at=datetime.now(UTC),
            scraped_at=datetime.now(UTC),
        )
        assert "..." in repr(msg)


class TestAttachmentModel:
    """Tests for the Attachment model."""

    async def test_create_attachment(self, session: AsyncSession) -> None:
        """Test creating an attachment."""
        guild = Guild(id=600, name="Test Guild")
        session.add(guild)
        await session.flush()

        channel = Channel(id=601, guild_id=600, name="general", type=0)
        session.add(channel)
        await session.flush()

        now = datetime.now(UTC)
        message = Message(
            id=602,
            channel_id=601,
            content="",
            clean_content="",
            created_at=now,
            scraped_at=now,
        )
        session.add(message)
        await session.flush()

        attachment = Attachment(
            id=700,
            message_id=602,
            filename="image.png",
            content_type="image/png",
            size=1024,
            url="https://cdn.discord.com/image.png",
        )
        session.add(attachment)
        await session.flush()

        result = await session.execute(select(Attachment).where(Attachment.id == 700))
        db_att = result.scalar_one()
        assert db_att.filename == "image.png"
        assert db_att.is_image is True
        assert db_att.is_video is False
        assert db_att.download_status == "pending"

    async def test_attachment_is_video(self) -> None:
        """Test is_video property."""
        att = Attachment(
            id=1,
            message_id=1,
            filename="video.mp4",
            content_type="video/mp4",
            size=5000,
            url="https://example.com/video.mp4",
        )
        assert att.is_video is True
        assert att.is_image is False


class TestReactionModel:
    """Tests for the Reaction model."""

    async def test_create_reaction(self, session: AsyncSession) -> None:
        """Test creating a reaction."""
        guild = Guild(id=800, name="Test Guild")
        session.add(guild)
        await session.flush()

        channel = Channel(id=801, guild_id=800, name="general", type=0)
        session.add(channel)
        await session.flush()

        now = datetime.now(UTC)
        message = Message(
            id=802,
            channel_id=801,
            content="React to this",
            clean_content="React to this",
            created_at=now,
            scraped_at=now,
        )
        session.add(message)
        await session.flush()

        reaction = Reaction(
            message_id=802,
            emoji_name="👍",
            count=5,
        )
        session.add(reaction)
        await session.flush()

        result = await session.execute(select(Reaction).where(Reaction.message_id == 802))
        db_reaction = result.scalar_one()
        assert db_reaction.emoji_name == "👍"
        assert db_reaction.count == 5
        assert db_reaction.emoji_display == "👍"

    async def test_reaction_emoji_display_id(self) -> None:
        """Test emoji_display with custom emoji (ID only)."""
        reaction = Reaction(
            message_id=1,
            emoji_id=123456,
            count=1,
        )
        assert "123456" in reaction.emoji_display
