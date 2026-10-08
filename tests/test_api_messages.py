"""The channel messages route over a seeded archive."""

from datetime import datetime, timedelta
from typing import Any

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


async def _page(client: AsyncClient, **params: int) -> dict[str, Any]:
    response = await client.get("/api/channels/10/messages", params=params)
    assert response.status_code == 200
    payload: dict[str, Any] = response.json()
    return payload


def _ids(payload: dict[str, Any]) -> list[str]:
    return [m["id"] for m in payload["messages"]]


async def test_channel_messages_open_at_the_newest(client: AsyncClient) -> None:
    payload = await _page(client, limit=2)
    assert _ids(payload) == ["3", "2"]
    assert payload["messages"][0]["author"]["username"] == "alice"
    assert (payload["total"], payload["has_more"]) == (3, True)
    assert (payload["before_id"], payload["after_id"]) == ("2", "3")


async def test_before_the_oldest_loaded_returns_the_adjacent_older_page(
    client: AsyncClient,
) -> None:
    first = await _page(client, limit=1)
    older = await _page(client, limit=1, before=int(first["before_id"]))
    assert (_ids(first), _ids(older)) == (["3"], ["2"])
    assert (older["total"], older["has_more"]) == (3, True)
    assert (older["before_id"], older["after_id"]) == ("2", "2")


async def test_has_more_is_false_at_the_channels_first_message(client: AsyncClient) -> None:
    last = await _page(client, limit=2, before=3)
    assert _ids(last) == ["2", "1"]
    assert last["has_more"] is False
    assert (await _page(client, limit=5))["has_more"] is False
    beyond = await _page(client, before=1)
    assert (_ids(beyond), beyond["has_more"], beyond["before_id"]) == ([], False, None)


async def test_after_returns_the_adjacent_newer_page_newest_first(client: AsyncClient) -> None:
    newer = await _page(client, limit=1, after=1)
    assert (_ids(newer), newer["has_more"]) == (["2"], True)
    newest = await _page(client, limit=5, after=1)
    assert (_ids(newest), newest["has_more"]) == (["3", "2"], False)


async def test_the_page_does_not_load_the_channel(
    client: AsyncClient, statements: list[str]
) -> None:
    """The route already knows its channel, so no statement reads ``channels``."""
    response = await client.get("/api/channels/10/messages")
    assert response.status_code == 200
    assert statements
    assert not any("channels" in statement for statement in statements)
