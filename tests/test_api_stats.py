"""The guild stats and activity routes over a seeded archive."""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from wumpus_archiver.models.attachment import Attachment
from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage import archive_reads
from wumpus_archiver.storage.database import Database
from wumpus_archiver.storage.repositories import CompletedScrapeRepository

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
        "since_last_scrape": None,
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
    """Guild, totals, attachments, channels, top channels, top users and the last scrape."""
    response = await client.get("/api/guilds/1/stats")
    assert response.status_code == 200
    assert len(statements) == 7
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
    assert len(statements) == 8


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


# ── The change since the last completed scrape job (ADR 0004) ───────────────

STARTED = datetime(2024, 4, 1, 10, 0)
COMPLETED = datetime(2024, 4, 1, 10, 5)


async def _add_rows(database: Database, *, first_id: int, channel_id: int) -> None:
    """What a scrape might add to guild one: a channel, a new author, two messages, a file."""
    async with database.session() as session:
        session.add(Channel(id=channel_id, guild_id=1, name=f"new{channel_id}", type=0))
        session.add(User(id=first_id, username=f"new{first_id}"))
        session.add_all(
            [
                Message(
                    id=first_id,
                    channel_id=channel_id,
                    author_id=first_id,
                    created_at=WHEN,
                    scraped_at=WHEN,
                ),
                Message(
                    id=first_id + 1, channel_id=10, author_id=100, created_at=WHEN, scraped_at=WHEN
                ),
            ]
        )
        session.add(Attachment(id=first_id, message_id=first_id, filename="g", size=1, url="u"))


async def _record_scrape(
    database: Database, guild_id: int, at_start: archive_reads.GuildTotals, completed: datetime
) -> None:
    async with database.session() as session:
        await CompletedScrapeRepository(session).record(
            guild_id, started_at=STARTED, at_start=at_start, completed_at=completed
        )


async def _totals(database: Database, guild_id: int) -> archive_reads.GuildTotals:
    async with database.session() as session:
        return await archive_reads.guild_totals(session, guild_id)


async def test_without_a_completed_scrape_there_is_no_change_rather_than_zero(
    client: AsyncClient,
) -> None:
    payload = (await client.get("/api/guilds/1/stats")).json()
    assert payload["since_last_scrape"] is None


async def test_the_change_is_what_was_added_since_the_last_completed_scrape_started(
    client: AsyncClient, database: Database
) -> None:
    """A scrape records the totals it started from; the stats subtract them from today's."""
    at_start = await _totals(database, 1)
    await _add_rows(database, first_id=500, channel_id=30)  # during the scrape
    await _record_scrape(database, 1, at_start, COMPLETED)
    await _add_rows(database, first_id=600, channel_id=31)  # after it

    payload = (await client.get("/api/guilds/1/stats")).json()
    assert payload["since_last_scrape"] == {
        "started_at": "2024-04-01T10:00:00",
        "completed_at": "2024-04-01T10:05:00",
        "messages": 4,
        "channels": 2,
        "authors": 2,
        "attachments": 2,
    }
    assert (
        payload["total_messages"] - at_start.messages,
        payload["total_channels"] - at_start.channels,
        payload["total_users"] - at_start.authors,
        payload["total_attachments"] - at_start.attachments,
    ) == (4, 2, 2, 2)


async def test_a_scrape_that_added_nothing_shows_a_true_zero(
    client: AsyncClient, database: Database
) -> None:
    await _record_scrape(database, 1, await _totals(database, 1), COMPLETED)
    change = (await client.get("/api/guilds/1/stats")).json()["since_last_scrape"]
    counts = (change["messages"], change["channels"], change["authors"], change["attachments"])
    assert counts == (0, 0, 0, 0)


async def test_the_latest_completed_scrape_of_this_guild_counts(
    client: AsyncClient, database: Database
) -> None:
    """An older scrape of the guild, and any scrape of another guild, are ignored."""
    await _record_scrape(database, 1, archive_reads.GuildTotals(), datetime(2024, 3, 1))
    await _record_scrape(database, 1, await _totals(database, 1), COMPLETED)
    await _record_scrape(database, 2, archive_reads.GuildTotals(), datetime(2024, 5, 1))
    await _add_rows(database, first_id=500, channel_id=30)

    change = (await client.get("/api/guilds/1/stats")).json()["since_last_scrape"]
    assert change["completed_at"] == "2024-04-01T10:05:00"
    assert change["messages"] == 2


async def test_an_archive_without_the_completed_scrapes_table_reads_as_never_scraped(
    client: AsyncClient, database: Database
) -> None:
    """An archive written before ADR 0004 is served as it is, until its next scrape."""
    async with database.session() as session:
        await session.execute(text("DROP TABLE completed_scrapes"))
    response = await client.get("/api/guilds/1/stats")
    assert response.status_code == 200
    assert response.json()["since_last_scrape"] is None
    assert response.json()["total_messages"] == 4


async def test_create_tables_gives_an_older_archive_the_completed_scrapes_table(
    database: Database,
) -> None:
    """What a scrape does first, so it can record itself in an archive from before ADR 0004."""
    async with database.session() as session:
        await session.execute(text("DROP TABLE completed_scrapes"))
    await database.create_tables()
    await _record_scrape(database, 1, archive_reads.GuildTotals(), COMPLETED)
    async with database.session() as session:
        assert await archive_reads.last_completed_scrape(session, 1) is not None

