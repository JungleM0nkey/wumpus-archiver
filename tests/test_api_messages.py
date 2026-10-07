"""The channel messages route over a seeded archive."""

from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient

from wumpus_archiver.models.channel import Channel
from wumpus_archiver.models.guild import Guild
from wumpus_archiver.models.message import Message
from wumpus_archiver.models.user import User
from wumpus_archiver.storage.database import Database

WHEN = datetime(2024, 6, 1)


@pytest.fixture(autouse=True)
async def seeded(database: Database) -> None:
    async with database.session() as session:
        session.add(Guild(id=1, name="one"))
        session.add(Channel(id=10, guild_id=1, name="general", type=0))
        session.add(User(id=100, username="alice"))
        for message_id in (1, 2, 3):
            session.add(
                Message(
                    id=message_id,
                    channel_id=10,
                    author_id=100,
                    content=f"message {message_id}",
                    created_at=WHEN + timedelta(minutes=message_id),
                    scraped_at=WHEN,
                )
            )


async def test_channel_messages_open_at_the_oldest(client: AsyncClient) -> None:
    response = await client.get("/api/channels/10/messages", params={"limit": 2})
    assert response.status_code == 200
    payload = response.json()
    assert [m["id"] for m in payload["messages"]] == ["1", "2"]
    assert payload["messages"][0]["author"]["username"] == "alice"
    assert (payload["total"], payload["has_more"]) == (3, True)
    assert (payload["before_id"], payload["after_id"]) == ("1", "2")


async def test_the_page_does_not_load_the_channel(
    client: AsyncClient, statements: list[str]
) -> None:
    """The route already knows its channel, so no statement reads ``channels``."""
    response = await client.get("/api/channels/10/messages")
    assert response.status_code == 200
    assert statements
    assert not any("channels" in statement for statement in statements)
