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


def _counts_messages(statement: str) -> bool:
    """Whether a statement counts rows of ``messages``: ``count(*)`` over it as the outer FROM.

    The outer FROM is the first one outside parentheses, so a scalar subquery in the
    select list is not mistaken for it.
    """
    depth = 0
    for at, char in enumerate(statement):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0 and statement.startswith("FROM ", at):
            return "count(*)" in statement[:at] and statement.startswith("FROM messages", at)
    return False


async def test_guild_stats_reads_each_total_once(
    client: AsyncClient, statements: list[str]
) -> None:
    """Guild, channels, totals, attachments, top channels and top users: nothing thrown away."""
    response = await client.get("/api/guilds/1/stats")
    assert response.status_code == 200
    assert len(statements) == 6
    assert sum(map(_counts_messages, statements)) == 1
    assert not any("reactions" in statement for statement in statements)


async def test_more_than_ten_authors_add_the_top_users_count(
    client: AsyncClient, database: Database, statements: list[str]
) -> None:
    """The top users page then pays the one COUNT that ADR 0002 accepts."""
    async with database.session() as session:
        for n in range(10):
            session.add(User(id=200 + n, username=f"user{n}"))
            session.add(
                Message(
                    id=100 + n, channel_id=11, author_id=200 + n, created_at=WHEN, scraped_at=WHEN
                )
            )
    statements.clear()
    response = await client.get("/api/guilds/1/stats")
    payload = response.json()
    assert (payload["total_users"], len(payload["top_users"])) == (12, 10)
    assert len(statements) == 7


async def test_total_users_counts_authors_without_a_users_row(
    client: AsyncClient, database: Database
) -> None:
    """``total_users`` counts distinct non-null author ids, as before; ``top_users`` needs a row."""
    async with database.session() as session:
        session.add(Message(id=6, channel_id=11, author_id=999, created_at=WHEN, scraped_at=WHEN))
        session.add(Message(id=7, channel_id=11, author_id=None, created_at=WHEN, scraped_at=WHEN))
    payload = (await client.get("/api/guilds/1/stats")).json()
    assert (payload["total_messages"], payload["total_users"]) == (6, 3)
    assert [user["id"] for user in payload["top_users"]] == ["100", "101"]


async def test_top_channels_are_text_channels_only(client: AsyncClient, database: Database) -> None:
    """Categories, voice channels and threads are never among the most active channels."""
    async with database.session() as session:
        session.add_all(
            [
                Channel(id=13, guild_id=1, name="Text Channels", type=4, message_count=0),
                Channel(id=14, guild_id=1, name="Voice", type=2, message_count=50),
                Channel(id=15, guild_id=1, name="a thread", type=11, message_count=40),
                Channel(id=16, guild_id=1, name="announcements", type=5, message_count=2),
            ]
        )
    payload = (await client.get("/api/guilds/1/stats")).json()
    assert [channel["name"] for channel in payload["top_channels"]] == [
        "general",
        "announcements",
        "random",
        "news",
    ]
    assert payload["total_channels"] == 7
