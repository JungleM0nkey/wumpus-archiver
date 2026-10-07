"""The guild stats route over a seeded archive."""

from datetime import datetime

import pytest
from httpx import AsyncClient

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

WHEN = datetime(2024, 3, 1)

# (id, channel, author)
MESSAGES = [(1, 10, 100), (2, 10, 100), (3, 11, 101), (4, 10, None), (5, 20, 101)]


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    async with database.session() as session:
        session.add_all([Guild(id=1, name="one"), Guild(id=2, name="two")])
        session.add_all(
            [
                Channel(id=10, guild_id=1, name="general", type=0, message_count=3),
                Channel(id=11, guild_id=1, name="random", type=0, message_count=1),
                Channel(id=12, guild_id=1, name="news", type=0, message_count=1),
                Channel(id=20, guild_id=2, name="elsewhere", type=0, message_count=1),
            ]
        )
        session.add_all(
            [
                User(id=100, username="alice", global_name="Alice", avatar_url="a.png"),
                User(id=101, username="bob"),
            ]
        )
        for message_id, channel_id, author_id in MESSAGES:
            session.add(
                Message(
                    id=message_id,
                    channel_id=channel_id,
                    author_id=author_id,
                    created_at=WHEN,
                    scraped_at=WHEN,
                )
            )
        session.add(Attachment(id=900, message_id=3, filename="f", size=1, url="u"))


async def test_guild_stats(client: AsyncClient) -> None:
    response = await client.get("/api/guilds/1/stats")
    assert response.status_code == 200
    assert response.json() == {
        "guild_name": "one",
        "total_channels": 3,
        "total_messages": 4,
        "total_users": 2,
        "total_attachments": 1,
        "top_channels": [
            {"id": "10", "name": "general", "message_count": 3},
            {"id": "11", "name": "random", "message_count": 1},
            {"id": "12", "name": "news", "message_count": 1},
        ],
        "top_users": [
            {
                "id": "100",
                "username": "alice",
                "display_name": "Alice",
                "avatar_url": "a.png",
                "message_count": 2,
            },
            {
                "id": "101",
                "username": "bob",
                "display_name": "bob",
                "avatar_url": None,
                "message_count": 1,
            },
        ],
    }
