"""Tests for repository classes."""

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.reaction import Reaction
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.repositories import (
    AttachmentRepository,
    ChannelRepository,
    GuildRepository,
    MessageRepository,
    ReactionRepository,
    UserRepository,
)


class TestGuildRepository:
    """Tests for GuildRepository."""

    async def test_upsert_new_guild(self, session: AsyncSession) -> None:
        """Test inserting a new guild."""
        repo = GuildRepository(session)
        guild = Guild(id=1000, name="New Guild", member_count=50)
        result = await repo.upsert(guild)
        assert result.name == "New Guild"
        assert result.member_count == 50

    async def test_upsert_existing_guild(self, session: AsyncSession) -> None:
        """Test updating an existing guild."""
        repo = GuildRepository(session)

        guild = Guild(id=1001, name="Original", member_count=10)
        await repo.upsert(guild)
        await session.flush()

        updated = Guild(id=1001, name="Updated", member_count=20)
        result = await repo.upsert(updated)
        assert result.name == "Updated"
        assert result.member_count == 20

    async def test_get_by_id(self, session: AsyncSession) -> None:
        """Test fetching guild by ID."""
        repo = GuildRepository(session)
        guild = Guild(id=1002, name="Findable")
        await repo.upsert(guild)
        await session.flush()

        found = await repo.get_by_id(1002)
        assert found is not None
        assert found.name == "Findable"

    async def test_get_by_id_not_found(self, session: AsyncSession) -> None:
        """Test get_by_id returns None for missing guild."""
        repo = GuildRepository(session)
        result = await repo.get_by_id(999999)
        assert result is None

    async def test_update_scrape_metadata(self, session: AsyncSession) -> None:
        """Test atomic scrape metadata update."""
        repo = GuildRepository(session)
        guild = Guild(id=1003, name="Scrape Test")
        await repo.upsert(guild)
        await session.flush()

        await repo.update_scrape_metadata(1003)
        await session.flush()

        result = await repo.get_by_id(1003)
        assert result is not None
        assert result.scrape_count == 1
        assert result.first_scraped_at is not None
        assert result.last_scraped_at is not None

    async def test_update_scrape_metadata_increments(self, session: AsyncSession) -> None:
        """Test scrape_count increments on repeated calls."""
        repo = GuildRepository(session)
        guild = Guild(id=1004, name="Increment Test")
        await repo.upsert(guild)
        await session.flush()

        await repo.update_scrape_metadata(1004)
        await session.flush()
        await repo.update_scrape_metadata(1004)
        await session.flush()

        result = await repo.get_by_id(1004)
        assert result is not None
        assert result.scrape_count == 2


class TestChannelRepository:
    """Tests for ChannelRepository."""

    async def test_upsert_new_channel(self, session: AsyncSession) -> None:
        """Test inserting a new channel."""
        guild = Guild(id=2000, name="Channel Test Guild")
        session.add(guild)
        await session.flush()

        repo = ChannelRepository(session)
        channel = Channel(id=2001, guild_id=2000, name="general", type=0)
        result = await repo.upsert(channel)
        assert result.name == "general"

    async def test_upsert_existing_channel(self, session: AsyncSession) -> None:
        """Test updating an existing channel."""
        guild = Guild(id=2100, name="Update Test")
        session.add(guild)
        await session.flush()

        repo = ChannelRepository(session)
        channel = Channel(id=2101, guild_id=2100, name="old-name", type=0, position=0)
        await repo.upsert(channel)
        await session.flush()

        updated = Channel(id=2101, guild_id=2100, name="new-name", type=0, position=5)
        result = await repo.upsert(updated)
        assert result.name == "new-name"
        assert result.position == 5

    async def test_get_by_guild(self, session: AsyncSession) -> None:
        """Test fetching all channels for a guild."""
        guild = Guild(id=2200, name="Multi Channel")
        session.add(guild)
        await session.flush()

        repo = ChannelRepository(session)
        for i, name in enumerate(["general", "random", "dev"]):
            channel = Channel(id=2200 + i + 1, guild_id=2200, name=name, type=0)
            await repo.upsert(channel)
        await session.flush()

        channels = await repo.get_by_guild(2200)
        assert len(channels) == 3
        names = {c.name for c in channels}
        assert names == {"general", "random", "dev"}

    async def test_update_message_metadata(self, session: AsyncSession) -> None:
        """Test updating channel message metadata."""
        guild = Guild(id=2300, name="Meta Test")
        session.add(guild)
        await session.flush()

        repo = ChannelRepository(session)
        channel = Channel(id=2301, guild_id=2300, name="test", type=0)
        await repo.upsert(channel)
        await session.flush()

        await repo.update_message_metadata(2301, last_message_id=99999, increment=50)
        await session.flush()

        result = await repo.get_by_id(2301)
        assert result is not None
        assert result.last_message_id == 99999
        assert result.message_count == 50
        assert result.last_scraped_at is not None


class TestUserRepository:
    """Tests for UserRepository."""

    async def test_upsert_new_user(self, session: AsyncSession) -> None:
        """Test inserting a new user."""
        repo = UserRepository(session)
        user = User(id=3000, username="newuser", bot=False)
        result = await repo.upsert(user)
        assert result.username == "newuser"
        assert result.bot is False

    async def test_upsert_existing_user(self, session: AsyncSession) -> None:
        """Test updating an existing user."""
        repo = UserRepository(session)
        user = User(id=3001, username="oldname", bot=False)
        await repo.upsert(user)
        await session.flush()

        updated = User(id=3001, username="newname", global_name="New Name", bot=False)
        result = await repo.upsert(updated)
        assert result.username == "newname"
        assert result.global_name == "New Name"


class TestMessageRepository:
    """Tests for MessageRepository."""

    async def _setup_channel(self, session: AsyncSession) -> int:
        """Create a guild+channel and return channel ID."""
        guild = Guild(id=4000, name="Msg Test Guild")
        session.add(guild)
        await session.flush()

        channel = Channel(id=4001, guild_id=4000, name="msgs", type=0)
        session.add(channel)
        await session.flush()
        return 4001

    async def test_upsert_new_message(self, session: AsyncSession) -> None:
        """Test inserting a new message."""
        channel_id = await self._setup_channel(session)
        repo = MessageRepository(session)

        now = datetime.utcnow()
        msg = Message(
            id=5000,
            channel_id=channel_id,
            content="Hello",
            clean_content="Hello",
            created_at=now,
            scraped_at=now,
        )
        result = await repo.upsert(msg)
        assert result.content == "Hello"

    async def test_upsert_existing_message(self, session: AsyncSession) -> None:
        """Test updating an existing message (e.g., edited)."""
        channel_id = await self._setup_channel(session)
        repo = MessageRepository(session)

        now = datetime.utcnow()
        msg = Message(
            id=5001,
            channel_id=channel_id,
            content="Original",
            clean_content="Original",
            created_at=now,
            scraped_at=now,
        )
        await repo.upsert(msg)
        await session.flush()

        edited = Message(
            id=5001,
            channel_id=channel_id,
            content="Edited",
            clean_content="Edited",
            created_at=now,
            edited_at=now,
            pinned=False,
            scraped_at=now,
        )
        result = await repo.upsert(edited)
        assert result.content == "Edited"
        assert result.edited_at is not None

    async def test_get_by_channel(self, session: AsyncSession) -> None:
        """Test fetching messages by channel with limit."""
        channel_id = await self._setup_channel(session)
        repo = MessageRepository(session)

        now = datetime.utcnow()
        for i in range(5):
            msg = Message(
                id=5100 + i,
                channel_id=channel_id,
                content=f"Message {i}",
                clean_content=f"Message {i}",
                created_at=now,
                scraped_at=now,
            )
            await repo.upsert(msg)
        await session.flush()

        messages = await repo.get_by_channel(channel_id, limit=3)
        assert len(messages) == 3

    async def test_get_by_channel_pagination(self, session: AsyncSession) -> None:
        """Test message pagination with before_id."""
        channel_id = await self._setup_channel(session)
        repo = MessageRepository(session)

        now = datetime.utcnow()
        for i in range(5):
            msg = Message(
                id=5200 + i,
                channel_id=channel_id,
                content=f"Paginated {i}",
                clean_content=f"Paginated {i}",
                created_at=now,
                scraped_at=now,
            )
            await repo.upsert(msg)
        await session.flush()

        messages = await repo.get_by_channel(channel_id, before_id=5203)
        ids = {m.id for m in messages}
        assert 5203 not in ids
        assert 5204 not in ids

    async def test_bulk_upsert(self, session: AsyncSession) -> None:
        """Test bulk upsert of messages."""
        channel_id = await self._setup_channel(session)
        repo = MessageRepository(session)

        now = datetime.utcnow()
        messages = [
            Message(
                id=5300 + i,
                channel_id=channel_id,
                content=f"Bulk {i}",
                clean_content=f"Bulk {i}",
                created_at=now,
                scraped_at=now,
            )
            for i in range(3)
        ]
        results = await repo.bulk_upsert(messages)
        assert len(results) == 3


class TestAttachmentRepository:
    """Tests for AttachmentRepository."""

    async def _setup_message(self, session: AsyncSession) -> int:
        """Create guild+channel+message and return message ID."""
        guild = Guild(id=6000, name="Att Test Guild")
        session.add(guild)
        await session.flush()

        channel = Channel(id=6001, guild_id=6000, name="attachments", type=0)
        session.add(channel)
        await session.flush()

        now = datetime.utcnow()
        msg = Message(
            id=6002,
            channel_id=6001,
            content="",
            clean_content="",
            created_at=now,
            scraped_at=now,
        )
        session.add(msg)
        await session.flush()
        return 6002

    async def test_upsert_new_attachment(self, session: AsyncSession) -> None:
        """Test inserting a new attachment."""
        msg_id = await self._setup_message(session)
        repo = AttachmentRepository(session)

        att = Attachment(
            id=7000,
            message_id=msg_id,
            filename="test.txt",
            size=100,
            url="https://cdn.discord.com/test.txt",
            download_status="pending",
        )
        result = await repo.upsert(att)
        assert result.filename == "test.txt"
        assert result.download_status == "pending"

    async def test_upsert_existing_attachment(self, session: AsyncSession) -> None:
        """Test updating an existing attachment (e.g., marking downloaded)."""
        msg_id = await self._setup_message(session)
        repo = AttachmentRepository(session)

        att = Attachment(
            id=7001,
            message_id=msg_id,
            filename="photo.jpg",
            size=2048,
            url="https://cdn.discord.com/photo.jpg",
        )
        await repo.upsert(att)
        await session.flush()

        updated = Attachment(
            id=7001,
            message_id=msg_id,
            filename="photo.jpg",
            size=2048,
            url="https://cdn.discord.com/photo.jpg",
            local_path="/attachments/photo.jpg",
            download_status="downloaded",
            content_hash="abc123",
        )
        result = await repo.upsert(updated)
        assert result.download_status == "downloaded"
        assert result.local_path == "/attachments/photo.jpg"


class TestReactionRepository:
    """Tests for ReactionRepository."""

    async def _setup_message(self, session: AsyncSession) -> int:
        """Create guild+channel+message and return message ID."""
        guild = Guild(id=8000, name="React Test Guild")
        session.add(guild)
        await session.flush()

        channel = Channel(id=8001, guild_id=8000, name="reactions", type=0)
        session.add(channel)
        await session.flush()

        now = datetime.utcnow()
        msg = Message(
            id=8002,
            channel_id=8001,
            content="React!",
            clean_content="React!",
            created_at=now,
            scraped_at=now,
        )
        session.add(msg)
        await session.flush()
        return 8002

    async def test_upsert_new_reaction(self, session: AsyncSession) -> None:
        """Test inserting a new reaction."""
        msg_id = await self._setup_message(session)
        repo = ReactionRepository(session)

        reaction = Reaction(
            message_id=msg_id,
            emoji_name="🎉",
            count=3,
        )
        result = await repo.upsert(reaction)
        assert result.emoji_name == "🎉"
        assert result.count == 3

    async def test_upsert_existing_reaction_updates_count(self, session: AsyncSession) -> None:
        """Test updating reaction count on re-scrape."""
        msg_id = await self._setup_message(session)
        repo = ReactionRepository(session)

        reaction = Reaction(message_id=msg_id, emoji_name="👍", count=1)
        await repo.upsert(reaction)
        await session.flush()

        updated = Reaction(message_id=msg_id, emoji_name="👍", count=10)
        result = await repo.upsert(updated)
        assert result.count == 10
