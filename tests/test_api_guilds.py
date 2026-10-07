"""The guild list, guild detail and channel list routes over a seeded archive."""

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select

from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.storage.database import Database

WHEN = datetime(2024, 5, 1, 12, 0, 0)

# (guild, [(channel, position, message count)])
GUILDS: dict[int, list[tuple[int, int, int]]] = {
    1: [(11, 2, 3), (12, 0, 0), (13, 2, 1)],
    2: [(21, 0, 2)],
    3: [],
    4: [(41, 5, 4), (42, 1, 1)],
}


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    next_id = 1000
    async with database.session() as session:
        for guild_id, channels in GUILDS.items():
            session.add(Guild(id=guild_id, name=f"guild {guild_id}"))
            for channel_id, position, messages in channels:
                session.add(
                    Channel(
                        id=channel_id,
                        guild_id=guild_id,
                        name=f"c{channel_id}",
                        type=0,
                        position=position,
                    )
                )
                for _ in range(messages):
                    next_id += 1
                    session.add(
                        Message(id=next_id, channel_id=channel_id, created_at=WHEN, scraped_at=WHEN)
                    )


@pytest.fixture
def statements(database: Database) -> Iterator[list[str]]:
    seen: list[str] = []

    def record(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        seen.append(statement)

    engine = database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", record)
    yield seen
    event.remove(engine, "before_cursor_execute", record)


async def _live_counts(database: Database, guild_id: int) -> tuple[int, int]:
    async with database.session() as session:
        channels = await session.scalar(
            select(func.count()).select_from(Channel).where(Channel.guild_id == guild_id)
        )
        messages = await session.scalar(
            select(func.count())
            .select_from(Message)
            .join(Channel, Message.channel_id == Channel.id)
            .where(Channel.guild_id == guild_id)
        )
    return channels or 0, messages or 0


async def test_guild_list_counts_equal_live_counts(client: AsyncClient, database: Database) -> None:
    response = await client.get("/api/guilds")
    assert response.status_code == 200
    payload = response.json()
    assert [g["id"] for g in payload] == [str(g) for g in GUILDS]
    for entry in payload:
        live = await _live_counts(database, int(entry["id"]))
        assert (entry["channel_count"], entry["message_count"]) == live


async def test_guild_list_issues_three_statements(
    client: AsyncClient, statements: list[str]
) -> None:
    response = await client.get("/api/guilds")
    assert response.status_code == 200
    assert len(statements) == 3


async def test_guild_detail(client: AsyncClient, database: Database) -> None:
    response = await client.get("/api/guilds/1")
    assert response.status_code == 200
    payload = response.json()
    assert [c["id"] for c in payload["channels"]] == ["12", "11", "13"]
    assert (payload["channel_count"], payload["message_count"]) == await _live_counts(database, 1)


@pytest.mark.parametrize(
    ("guild_id", "expected"), [(1, ["12", "11", "13"]), (3, []), (4, ["42", "41"]), (9, [])]
)
async def test_channel_list(client: AsyncClient, guild_id: int, expected: list[str]) -> None:
    response = await client.get(f"/api/guilds/{guild_id}/channels")
    assert response.status_code == 200
    payload = response.json()
    assert [c["id"] for c in payload["channels"]] == expected
    assert payload["total"] == len(expected)
