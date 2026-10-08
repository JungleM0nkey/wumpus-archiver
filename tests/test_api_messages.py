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
# #63 (Browse's Pinned tab): the pinned messages.
PINNED = {1, 3}


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
                    pinned=message_id in PINNED,
                )
            )


async def _page(client: AsyncClient, **params: int | str) -> dict[str, Any]:
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


async def test_around_opens_on_a_message_with_its_neighbours(client: AsyncClient) -> None:
    """A message link opens the reader on that message, newest first like any page."""
    page = await _page(client, limit=3, around=2)
    assert _ids(page) == ["3", "2", "1"]
    assert (page["has_more"], page["has_newer"]) == (False, False)
    assert (page["before_id"], page["after_id"]) == ("1", "3")


async def test_around_says_what_remains_on_either_side(client: AsyncClient) -> None:
    middle = await _page(client, limit=1, around=2)
    assert (_ids(middle), middle["has_more"], middle["has_newer"]) == (["2"], True, True)
    assert middle["total"] == 3
    newest = await _page(client, limit=2, around=3)
    assert (_ids(newest), newest["has_more"], newest["has_newer"]) == (["3", "2"], True, False)


async def test_around_an_unknown_message_opens_at_the_newest(client: AsyncClient) -> None:
    page = await _page(client, limit=2, around=999)
    assert _ids(page) == ["3", "2"]
    assert (page["has_more"], page["has_newer"]) == (True, False)


async def test_has_newer_is_only_set_around_a_message(client: AsyncClient) -> None:
    assert (await _page(client, limit=1))["has_newer"] is None


@pytest.mark.parametrize("cursor", ["before", "after"])
async def test_around_does_not_combine_with_a_cursor(client: AsyncClient, cursor: str) -> None:
    response = await client.get("/api/channels/10/messages", params={"around": 2, cursor: 1})
    assert response.status_code == 400


async def test_pinned_lists_only_the_channels_pinned_messages(client: AsyncClient) -> None:
    """Browse's Pinned tab (#63): the pinned messages, newest first, and their total."""
    page = await _page(client, pinned="true")
    assert _ids(page) == ["3", "1"]
    assert all(m["pinned"] for m in page["messages"])
    assert (page["total"], page["has_more"]) == (2, False)


async def test_pinned_pages_with_a_cursor_and_totals_the_pinned(client: AsyncClient) -> None:
    first = await _page(client, pinned="true", limit=1)
    assert (_ids(first), first["total"], first["has_more"]) == (["3"], 2, True)
    older = await _page(client, pinned="true", limit=1, before=int(first["before_id"]))
    assert (_ids(older), older["total"], older["has_more"]) == (["1"], 2, False)


async def test_pinned_false_lists_the_rest(client: AsyncClient) -> None:
    page = await _page(client, pinned="false")
    assert (_ids(page), page["total"]) == (["2"], 1)


async def test_without_pinned_every_message_is_listed(client: AsyncClient) -> None:
    assert (await _page(client))["total"] == 3


async def test_pinned_does_not_combine_with_around(client: AsyncClient) -> None:
    response = await client.get("/api/channels/10/messages", params={"around": 2, "pinned": "true"})
    assert response.status_code == 400


# ── Replies (#61) ────────────────────────────────────────────────────────────


async def _add_replies(database: Database) -> None:
    """Replies on general to 1, 2 and to messages elsewhere: one in #off-topic, one not archived."""
    async with database.session() as session:
        session.add(User(id=101, username="bob", global_name="Bob"))
        session.add(Channel(id=11, guild_id=1, name="off-topic", type=0))
        long = "A long line   of text\nthat goes on " + "and on " * 30
        session.add(
            Message(
                id=50,
                channel_id=11,
                author_id=101,
                content=long,
                clean_content=long,
                created_at=WHEN,
                scraped_at=WHEN,
            )
        )
        for message_id, minutes, refers_to in [(4, 4, 1), (5, 5, 2), (6, 6, 50), (7, 7, 999)]:
            session.add(
                Message(
                    id=message_id,
                    channel_id=10,
                    author_id=101,
                    content=f"reply {message_id}",
                    clean_content=f"reply {message_id}",
                    created_at=WHEN + timedelta(minutes=minutes),
                    reference_id=refers_to,
                    scraped_at=WHEN,
                )
            )


async def test_a_reply_carries_the_author_and_a_snippet_of_its_message(
    client: AsyncClient, database: Database
) -> None:
    await _add_replies(database)
    by_id = {m["id"]: m for m in (await _page(client))["messages"]}
    assert by_id["4"]["reference"] == {
        "id": "1",
        "channel_id": "10",
        "author": {
            "id": "100",
            "username": "alice",
            "discriminator": None,
            "global_name": None,
            "avatar_url": None,
            "bot": False,
            "display_name": "alice",
        },
        "snippet": "message 1",
    }
    # A message in another channel, its text on one line and cut with an ellipsis.
    elsewhere = by_id["6"]["reference"]
    assert (elsewhere["channel_id"], elsewhere["author"]["display_name"]) == ("11", "Bob")
    assert elsewhere["snippet"].startswith("A long line of text that goes on and on")
    assert len(elsewhere["snippet"]) == 120 and elsewhere["snippet"].endswith("…")
    # A reply to a message the archive does not hold keeps its id and has no reference.
    assert (by_id["7"]["reference_id"], by_id["7"]["reference"]) == ("999", None)
    assert by_id["1"]["reference"] is None


async def test_a_pages_references_are_read_in_one_statement(
    client: AsyncClient, database: Database, statements: list[str]
) -> None:
    """No N+1: four replies cost one statement more than a page without any."""
    await _add_replies(database)
    statements.clear()
    without = await client.get("/api/channels/10/messages", params={"before": 4})
    assert without.status_code == 200
    plain = len(statements)
    statements.clear()
    with_replies = await client.get("/api/channels/10/messages", params={"after": 3})
    assert [m["reference_id"] for m in with_replies.json()["messages"]] == ["999", "50", "2", "1"]
    assert len(statements) == plain + 1


async def test_a_reply_on_an_around_page_carries_its_reference(
    client: AsyncClient, database: Database
) -> None:
    await _add_replies(database)
    page = await _page(client, limit=3, around=5)
    reference = {m["id"]: m["reference"] for m in page["messages"]}["5"]
    assert (reference["id"], reference["snippet"]) == ("2", "message 2")
